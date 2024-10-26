from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, g, session
from flask_mailman import Mail, EmailMessage
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
import yfinance as yf
import bcrypt
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import pytz
import pandas as pd
import subprocess, os, json
import random, string
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Init ---------------------------------------------------------------------------------------------------------------------------
load_dotenv()  # Load environment variables from .env file

mail = Mail()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# MongoDB Configuration
# Your MongoDB credentials
username = os.getenv('MONGO_USERNAME')
password = os.getenv('MONGO_PASSWORD')

# URL-encode the credentials
encoded_username = quote_plus(username)
encoded_password = quote_plus(password)

# Build the MongoDB URI with encoded credentials
mongo_uri = f"mongodb+srv://{encoded_username}:{encoded_password}@asptest.uvb9c.mongodb.net/"

# Initialize MongoDB client
client = MongoClient(mongo_uri)
db = client['stock_app']
users_collection = db['users']
trades_collection = db['trades']

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Mailing
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mail.init_app(app)

# URLSafeTimedSerializer for token generation and verification
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

@app.before_request
def load_recent_changes():
    g.recent_changes = get_recent_changes()

# Sidebar Recent Changes
def get_recent_changes():
    json_path = os.path.join(os.getcwd(), 'static', 'json', 'recent_changes.json')
    
    # Load the JSON data from the file
    with open(json_path, 'r') as file:
        data = json.load(file)
        
    # Return only the 5 most recent changes
    return data

# SQL Management
# MongoDB User Model
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.email = user_data['email']
        self.password = user_data['password']
        self.first_name = user_data['first_name']
        self.last_name = user_data['last_name']
        self.date_of_birth = user_data.get('date_of_birth')
        self.phone_number = user_data.get('phone_number')
        self.portfolio_value = user_data.get('portfolio_value', 0.0)
        self.portfolio_locked = user_data.get('portfolio_locked', False)
        self.confirmation_number = user_data.get('confirmation_number')
        self.email_confirmed = user_data.get('email_confirmed', False)
        self.portfolio_initial = user_data.get('portfolio_initial', 0.0)


@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({"_id": ObjectId(user_id)})
    if user_data:
        return User(user_data)
    return None

# Index ---------------------------------------------------------------------------------------------------------------------------------
@app.route('/')
def start():
    if current_user.is_authenticated:
        trades = list(trades_collection.find({"user_id": current_user.id}))
        updated_user = users_collection.find_one({"_id": ObjectId(current_user.id)})
        portfolio_value = updated_user['portfolio_value']
        holdings = calculate_current_holdings(current_user.id)
        return render_template('index.html')
    else:
        return render_template('index.html')


# Login / Register / Logout
@app.route('/register', methods=['GET', 'POST'])
def register():
    confirmation = False
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        date_of_birth = request.form.get('dob')
        phone_number = request.form.get('phone')

        user = users_collection.find_one({"email": email})
        if user:
            flash('Email address already exists', 'error')
            return redirect(url_for('register'))

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        confirmation_number = generate_confirmation_number()
        
        msg = EmailMessage(
            "Confirm Your Email for Axiom Stock Picks",
            f"""
            Hi there,

            Welcome to Axiom Stock Picks! 
            Your confirmation code: {confirmation_number}
            """,
            app.config['MAIL_USERNAME'],
            [email]
        )
        msg.send()

        flash('A confirmation email has been sent.', 'success')
        
        new_user = {
            "email": email,
            "password": hashed_password.decode('utf-8'),
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": datetime.strptime(date_of_birth, '%Y-%m-%d').date() if date_of_birth else None,
            "phone_number": phone_number,
            "portfolio_value": 0.0,
            "portfolio_locked": False,
            
            # Adding Portfolio Initial
            "portfolio_initial": 0.0,
            "confirmation_number": confirmation_number,
            "email_confirmed": False
        }
        
        users_collection.insert_one(new_user)
        confirmation = True

    return render_template('register.html', confirmation=confirmation)

# Confirm Email ---------------------------------------------------------------------------------------------------------------------------------
@app.route('/confirm', methods=['POST'])
def confirm():
    confirmation_number = request.form.get('confirmation_number')
    user = users_collection.find_one({"confirmation_number": confirmation_number})

    if user:
        users_collection.update_one({"_id": user["_id"]}, {"$set": {"email_confirmed": True}})
        flash('Email confirmed successfully.', 'success')
        return redirect(url_for('login'))
    else:
        flash('Invalid confirmation number.', 'error')
        return redirect(url_for('register'))
    
# Login ---------------------------------------------------------------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = users_collection.find_one({"email": email})
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            flash('Invalid email or password', 'error')
            return redirect(url_for('login'))

        # Store the phone number in the session
        session['phone_number'] = user.get('phone_number')

        login_user(User(user))
        return redirect(url_for('home'))
    return render_template('login.html')

# Logout ---------------------------------------------------------------------------------------------------------------------------------
@app.route('/logout', methods=['POST', 'GET'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def generate_confirmation_number():
    return ''.join(random.choices(string.digits, k=6))


# Paper Trading Page 
@app.route('/home')
@login_required
def home():
    trades = list(trades_collection.find({"user_id": current_user.id}))
    holdings = calculate_current_holdings(current_user.id)
    portfolio_value = current_user.portfolio_value
    portfolio_initial = current_user.portfolio_initial
    
    return render_template('paper_trade.html', trades=trades, portfolio_value=portfolio_value, portfolio_initial=portfolio_initial, holdings=holdings)


# Calculate Holdings ---------------------------------------------------------------------------------------------------------------------------------
def calculate_current_holdings(user_id):
    trades = list(trades_collection.find({"user_id": user_id}))
    holdings = {}

    for trade in trades:
        if trade['action'] == 'BUY':
            if trade['ticker'] in holdings:
                holdings[trade['ticker']]['quantity'] += trade['quantity']
                holdings[trade['ticker']]['total_cost'] += trade['total_value']
            else:
                holdings[trade['ticker']] = {
                    'quantity': trade['quantity'],
                    'total_cost': trade['total_value']
                }
        elif trade['action'] == 'SELL':
            if trade['ticker'] in holdings:
                holdings[trade['ticker']]['quantity'] -= trade['quantity']
                holdings[trade['ticker']]['total_cost'] -= trade['total_value']
                if holdings[trade['ticker']]['quantity'] <= 0:
                    del holdings[trade['ticker']]

    result = []
    for ticker, data in holdings.items():
        average_price = data['total_cost'] / data['quantity'] if data['quantity'] > 0 else 0
        try:
            stock = yf.Ticker(ticker)
            stock_info = stock.info
            last_price = stock_info.get('currentPrice', 0)
        except Exception as e:
            last_price = 0

        result.append({
            'ticker': ticker,
            'quantity': data['quantity'],
            'average_price': average_price,
            'last_price': last_price
        })

    return result

# Trade ---------------------------------------------------------------------------------------------------------------------------------
@app.route('/trade', methods=['POST'])
@login_required
def trade():
    ticker = request.form.get('ticker')
    action = request.form.get('action')
    quantity = int(request.form.get('quantity'))

    try:
        stock = yf.Ticker(ticker)
        stock_info = stock.info
        price = stock_info['currentPrice']
    except KeyError:
        flash('Error: Unable to retrieve the current stock price.', 'error')
        return redirect(url_for('home'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('home'))

    rounded_price = round(price, 2)
    total_value = round(rounded_price * quantity, 2)

    user = users_collection.find_one({"_id": ObjectId(current_user.id)})

    if action == 'BUY':
        if user['portfolio_value'] < total_value:
            flash('Error: Insufficient portfolio value.', 'error')
            return redirect(url_for('home'))

        users_collection.update_one({"_id": ObjectId(current_user.id)}, {"$inc": {"portfolio_value": -total_value}})

    elif action == 'SELL':
        current_balance = calculate_stock_balance(current_user.id, ticker)
        if quantity > current_balance:
            flash(f'Error: Cannot sell more stocks than you own. Balance: {current_balance}', 'error')
            return redirect(url_for('home'))

        users_collection.update_one({"_id": ObjectId(current_user.id)}, {"$inc": {"portfolio_value": total_value}})

    new_trade = {
        "user_id": current_user.id,
        "ticker": ticker,
        "action": action,
        "price": rounded_price,
        "quantity": quantity,
        "total_value": total_value,
        "date": datetime.now(pytz.timezone('US/Eastern')).replace(microsecond=0)
    }
    trades_collection.insert_one(new_trade)

    updated_balance = calculate_stock_balance(current_user.id, ticker)
    flash(f'{action} executed for {quantity} stocks of {ticker} at ${rounded_price}. Remaining stocks: {updated_balance}', 'success')

    return redirect(url_for('home'))

# Update Portfolio -------------------------------------------------------------------------------------------------------------------------------
@app.route('/update_portfolio', methods=['POST'])
@login_required
def update_portfolio():
    portfolio_value = request.form.get('portfolio_value', type=float)

    if portfolio_value is None or portfolio_value < 0:
        flash('Invalid portfolio value. Please enter a valid number.', 'error')
        return redirect(url_for('home'))

    # Get the current user document
    user = users_collection.find_one({"_id": ObjectId(current_user.id)})

    # Check if 'portfolio_initial' is set or is still at the default value of 0.0
    if not user.get('portfolio_initial') or user['portfolio_initial'] == 0.0:
        # Set the 'portfolio_initial' to the first portfolio value
        users_collection.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": {"portfolio_initial": portfolio_value}}
        )

    # Update the user's portfolio value and lock the portfolio
    users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$set": {"portfolio_value": portfolio_value, "portfolio_locked": True}}
    )

    flash(f'Portfolio value updated to ${portfolio_value:.2f} and locked.', 'success')
    return redirect(url_for('home'))

# Reset Portfolio ---------------------------------------------------------------------------------------------------------------------------------
@app.route('/reset_portfolio', methods=['POST'])
@login_required
def reset_portfolio():
    users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {
            "$set": {
                "portfolio_value": 0.0,
                "portfolio_locked": False,
                "portfolio_initial": 0.0  # Reset the initial portfolio value as well
            }
        }
    )
    trades_collection.delete_many({"user_id": current_user.id})
    flash('Portfolio reset and trade history cleared.', 'success')
    return redirect(url_for('home'))

def calculate_stock_balance(user_id, ticker):
    trades = list(trades_collection.find({"user_id": user_id, "ticker": ticker}))
    balance = 0
    for trade in trades:
        if trade['action'] == 'BUY':
            balance += trade['quantity']
        elif trade['action'] == 'SELL':
            balance -= trade['quantity']
    return balance

# Basic Pages ---------------------------------------------------------------------------------------------------------------
@app.route('/housing')
def housing():
    return render_template('pubs/housing.html')

@app.route('/stock-viewer')
def generic():
    return render_template('stock_viewer.html')

@app.route('/articles')
def article():
    return render_template('articles.html')

@app.route('/asp-portfolio')
def portfolio():
    return render_template('asp_portfolio.html')

@app.route('/palo-alto-panw')
def palo_alto():
    return render_template('palo_alto_PANW.html')

@app.route('/b-and-b-bro')
def b_and_b():
    return render_template('brown_and_brown_BRO.html')

@app.route('/danaher-dhr')
def danaher():
    return render_template('danaher_DHR.html')

@app.route('/brookefield-bam')
def brookefield():
    return render_template('brookefield_BAM.html')

@app.route('/nasdaq-ndaq')
def nasdaq():
    return render_template('ndaq.html')

@app.route('/cibc-cm')
def cibc():
    return render_template('cibc_CM.html')

@app.route('/tesla-tsla')
def tesla():
    return render_template('tesla_TSLA.html')

@app.route('/QTI')
def QTI():
    return render_template('QTI.html')

@app.route('/settings')
def settings():
    
    # Retrieve the phone number from the session
    phone_number = session.get('phone_number', 'Phone number not available')
    phone_number = format_phone_number(phone_number)
    
    return render_template('settings.html', phone_number=phone_number)

@app.route('/portfolio-updates')
def portfolio_updates():
    return render_template('portfolio_updates.html')

# Related to ASP Portfolio --------------------------------------------------------------------------------------------------
def fetch_current_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="1d")
        if not data.empty:
            return data['Close'].iloc[-1]  # Get the last closing price
        return None
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None

@app.route('/asp-data')
def get_asp_data():
    # Load Excel data
    df = pd.read_excel('static/documents/asp_portfolio.xlsx')
    
    # Track indexes where 'Raised Stop Loss' values are changed
    df['Raised Stop Loss Changed'] = df["Raised Stop Loss"] > 0
    
    # Update 'Stop Loss' where 'Raised Stop Loss' > 0
    df.loc[df["Raised Stop Loss"] > 0, "Stop Loss"] = df["Raised Stop Loss"]
    
    # Track indexes where 'Raised Stop Loss' values are changed
    df['Hit-T1?'] = df["Hit-T1"] > 0
    df['Hit-T2?'] = df["Hit-T2"] > 0
    
    # Update current prices and perform calculations
    df['Current Price'] = df['Ticker'].apply(fetch_current_price)
    df['Unrealized Gain/Loss'] = (df['Current Price'] - df['Price Bought']) / df['Price Bought'] * 100
    df['% To T1'] = (df['Target 1'] - df['Current Price']) / df['Current Price'] * 100
    df['% To T2'] = (df['Target 2'] - df['Current Price']) / df['Current Price'] * 100
    df['% To Stop Loss'] = (df['Stop Loss'] - df['Current Price']) / df['Current Price'] * 100
        
    # Round all numeric values to 2 decimal places
    df = df.round(2)

    # Format percentage columns with '%' sign
    df['Unrealized Gain/Loss'] = df['Unrealized Gain/Loss'].astype(str) + '%'
    df['% To T1'] = df['% To T1'].astype(str) + '%'
    df['% To T2'] = df['% To T2'].astype(str) + '%'
    df['% To Stop Loss'] = df['% To Stop Loss'].astype(str) + '%'

    # Format currency columns with '$' sign
    df['Price Bought'] = df['Price Bought'].apply(lambda x: f'${x:.2f}')
    df['Current Price'] = df['Current Price'].apply(lambda x: f'${x:.2f}')
    df['Stop Loss'] = df['Stop Loss'].apply(lambda x: f'${x:.2f}')
    df['Target 1'] = df['Target 1'].apply(lambda x: f'${x:.2f}')
    df['Target 2'] = df['Target 2'].apply(lambda x: f'${x:.2f}')

    # Convert DataFrame to JSON
    data = df.to_dict(orient='records')
    return jsonify(data)

@app.route('/qti-data')
def get_QTI_data():
    # Load Excel data
    df = pd.read_excel('static/documents/qti_portfolio.xlsx')
    
    # Define a function to calculate unrealized gain/loss based on type
    def calculate_unrealized_gain_loss(row):
        if row['Type'] == 'Buy':
            return (row['Current Price'] - row['Price Bought']) / row['Price Bought'] * 100
        elif row['Type'] == 'Short':
            return (row['Price Bought'] - row['Current Price']) / row['Price Bought'] * 100
        return 0

    # Apply the calculation function to each row
    df['Current Price'] = df['Ticker'].apply(fetch_current_price)
    df['Unrealized Gain/Loss'] = df.apply(calculate_unrealized_gain_loss, axis=1)
    
    # Round all numeric values to 2 decimal places
    df = df.round(2)

    # Format percentage columns with '%' sign
    df['Unrealized Gain/Loss'] = df['Unrealized Gain/Loss'].astype(str) + '%'
    
    # Format currency columns with '$' sign
    df['Price Bought'] = df['Price Bought'].apply(lambda x: f'${x:.2f}')
    df['Current Price'] = df['Current Price'].apply(lambda x: f'${x:.2f}')
    df['Stop Loss'] = df['Stop Loss'].apply(lambda x: f'${x:.2f}')

    # Convert DataFrame to JSON
    data = df.to_dict(orient='records')
    return jsonify(data)


# Stock Data
@app.route('/run-python')
def run_python():
    ticker = request.args.get('ticker')
    result = subprocess.run(['python', 'downloader.py', ticker], capture_output=True, text=True)
    return result.stdout


# Utils
def format_phone_number(phone):
    if len(phone) == 10 and phone.isdigit():  
        return f"{phone[:3]} - {phone[3:6]} - {phone[6:]}"
    return phone 

# Run
if __name__ == '__main__':
    app.run(debug=True)    
