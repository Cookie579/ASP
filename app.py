from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, g, session
from flask_mailman import Mail, EmailMessage
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
import yfinance as yf
import bcrypt
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import pytz
import pandas as pd
import subprocess, os, json
import random, string


# Init ---------------------------------------------------------------------------------------------------------------------------
mail = Mail()
app = Flask(__name__)
app.config['SECRET_KEY'] = '+CfgC^B^]+<j0(B*&Tti:3|Muf3-1L'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Mailing
app.config['MAIL_SERVER']='smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'warrenharold119@gmail.com'
app.config['MAIL_PASSWORD'] = 'tpkq mqzx fdby eyjh'
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
    # Construct the path to the JSON file in the static folder
    json_path = os.path.join(os.getcwd(), 'static', 'json', 'recent_changes.json')
    
    # Load the JSON data from the file
    with open(json_path, 'r') as file:
        data = json.load(file)
        
    # Return only the 5 most recent changes
    return data[:5]

# SQL Management
# SQL Database
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

    # username = db.Column(db.String(150), unique=True, nullable=False)
    
    first_name = db.Column(db.String(150), nullable=False)
    last_name = db.Column(db.String(150))
    date_of_birth = db.Column(db.Date)
    phone_number = db.Column(db.String(50))
    portfolio_value = db.Column(db.Float, default=0.0)
    portfolio_locked = db.Column(db.Boolean, default=False)
    confirmation_number = db.Column(db.String(50), default=False)
    email_confirmed = db.Column(db.Boolean, default=False)

class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    action = db.Column(db.String(4), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_value = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(pytz.timezone('US/Eastern')).replace(microsecond=0))

# SQL Retriever
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Index ---------------------------------------------------------------------------------------------------------------------------------
@app.route('/')
def start():

    if current_user.is_authenticated:
        trades = Trade.query.filter_by(user_id=current_user.id).all()

        Session = sessionmaker(bind=db.engine)
        session = Session()
        updated_user = session.get(User, current_user.id)

        portfolio_value = updated_user.portfolio_value
        print(f"Portfolio Value in Home Route: {portfolio_value}")

        holdings = calculate_current_holdings(current_user.id)

        return render_template('index.html')
        # return render_template('home.html', trades=trades, portfolio_value=portfolio_value, holdings=holdings, theme=theme)
    else:
        return render_template('index.html') 


# Login / Register / Logout
# Register a new account
@app.route('/register', methods=['GET', 'POST'])
def register():
    confirmation = False  # Default to False
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        date_of_birth = request.form.get('dob')
        phone_number = request.form.get('phone')

        # Check if the user already exists
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email address already exists', 'error')
            return redirect(url_for('register'))

        # Hash the password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # Create new user
        confirmation_number = generate_confirmation_number()
        new_user = User(
            email=email,
            password=hashed_password.decode('utf-8'),
            first_name=first_name,
            last_name=last_name,
            date_of_birth=datetime.strptime(date_of_birth, '%Y-%m-%d').date() if date_of_birth else None,
            phone_number=phone_number,
            email_confirmed=False,
            confirmation_number=confirmation_number  
        )
        db.session.add(new_user)
        db.session.commit()

        # Send confirmation email
        msg = EmailMessage(
            "Confirm Your Email for Axiom Stock Picks",
            f"""
            Hi there,

            Welcome to **Axiom Stock Picks**, where we bring you elite stock picks and market insights!

            To complete your registration, please confirm your email by entering the following confirmation code on the website:

            **Your Confirmation Code:** {confirmation_number}

            Thank you for joining us! If you have any questions or need assistance, feel free to reach out to our support team.

            Looking forward to helping you make informed investment decisions!

            Best regards,
            The Axiom Stock Picks Team
            
            [Support Contact Info]
            """,
            app.config['MAIL_USERNAME'],
            [email]
        )
        msg.send()

        flash('A confirmation email has been sent to your email address. Please confirm to complete the registration.', 'info')
        confirmation = True  

    return render_template('register.html', confirmation=confirmation)


@app.route('/confirm', methods=['POST'])
def confirm():
    confirmation_number = request.form.get('confirmation_number')
    user = User.query.filter_by(confirmation_number=confirmation_number).first()
    
    print("Confirmation number", confirmation_number)

    if user:
        user.email_confirmed = True
        db.session.commit()
        flash('Email confirmed successfully. You can now log in.', 'success')
        return redirect(url_for('login'))
    else:
        flash('Invalid confirmation number. Please try again.', 'error')
        return redirect(url_for('register'))
    
# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            flash('Invalid email or password', 'error')
            return redirect(url_for('login'))

        login_user(user)
        return redirect(url_for('home')) 
    return render_template('login.html')


# Logout
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
    trades = Trade.query.filter_by(user_id=current_user.id).all()

    # Your existing logic for calculating holdings and portfolio value
    holdings = calculate_current_holdings(current_user.id)
    portfolio_value = current_user.portfolio_value

    return render_template('paper_trade.html', trades=trades, portfolio_value=portfolio_value, holdings=holdings)


def calculate_current_holdings(user_id):
    trades = Trade.query.filter_by(user_id=user_id).all()
    holdings = {}

    for trade in trades:
        if trade.action == 'BUY':
            if trade.ticker in holdings:
                holdings[trade.ticker]['quantity'] += trade.quantity
                holdings[trade.ticker]['total_cost'] += trade.total_value
            else:
                holdings[trade.ticker] = {
                    'quantity': trade.quantity,
                    'total_cost': trade.total_value
                }
        elif trade.action == 'SELL':
            if trade.ticker in holdings:
                holdings[trade.ticker]['quantity'] -= trade.quantity
                holdings[trade.ticker]['total_cost'] -= trade.total_value
                if holdings[trade.ticker]['quantity'] <= 0:
                    del holdings[trade.ticker]

    result = []
    for ticker, data in holdings.items():
        average_price = data['total_cost'] / data['quantity'] if data['quantity'] > 0 else 0

        # Get the current price of the stock
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
        flash('Error: Unable to retrieve the current stock price. Please check the ticker symbol and try again.', 'error')
        return redirect(url_for('home'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('home'))

    rounded_price = round(price, 2)
    total_value = round(rounded_price * quantity, 2)

    if action == 'BUY':
        if current_user.portfolio_value < total_value:
            flash('Error: Insufficient portfolio value to execute this trade.', 'error')
            return redirect(url_for('home'))
        
        current_user.portfolio_value -= total_value

    elif action == 'SELL':
        current_balance = calculate_stock_balance(current_user.id, ticker)
        if quantity > current_balance:
            flash(f'Error: Cannot sell more stocks than you own. Current stock balance for {ticker}: {current_balance} stocks', 'error')
            return redirect(url_for('home'))
        
        current_user.portfolio_value += total_value

    new_trade = Trade(user_id=current_user.id, ticker=ticker, action=action, price=rounded_price, quantity=quantity, total_value=total_value)
    db.session.add(new_trade)

    db.session.merge(current_user)
    db.session.commit()

    updated_user = User.query.get(current_user.id)
    print(f"Database Portfolio Value after {action}: {updated_user.portfolio_value}")

    updated_balance = calculate_stock_balance(current_user.id, ticker)
    flash(f'{action} executed for {quantity} stocks of {ticker} at ${rounded_price:.2f} each. Total value: ${total_value:.2f}. Remaining stocks of {ticker}: {updated_balance}', 'success')

    return redirect(url_for('home'))


@app.route('/update_portfolio', methods=['POST', 'GET'])
@login_required
def update_portfolio():
    if current_user.portfolio_locked:
        flash('Portfolio is locked. Please reset it to make changes.', 'error')
        return redirect(url_for('home'))

    Trade.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()

    portfolio_value = request.form.get('portfolio_value', type=float)
    print("Portfolio Value =", portfolio_value)

    if portfolio_value is None:
        flash('Invalid portfolio value.', 'error')
        return redirect(url_for('home'))

    current_user.portfolio_value = portfolio_value
    current_user.portfolio_locked = True
    db.session.commit()

    updated_user = User.query.get(current_user.id)
    print(f"Updated Portfolio Value: {updated_user.portfolio_value}")
    print(f"Portfolio Locked: {updated_user.portfolio_locked}")

    PV = updated_user.portfolio_value
    print('PV=', PV)

    flash('Portfolio updated and trade history cleared.', 'success')
    return redirect(url_for('home'))


@app.route('/reset_portfolio', methods=['POST'])
@login_required
def reset_portfolio():
    # Clear the user's portfolio value and unlock it
    user = User.query.get(current_user.id)
    user.portfolio_value = 0.0
    user.portfolio_locked = False
    db.session.commit()

    # Clear trade history
    Trade.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()

    # Debugging
    updated_user = User.query.get(current_user.id)
    print(f"Reset Portfolio Value: {updated_user.portfolio_value}")
    print(f"Portfolio Locked: {updated_user.portfolio_locked}")

    flash('Portfolio reset and trade history cleared.', 'success')
    return redirect(url_for('home'))


def calculate_stock_balance(user_id, ticker):
    trades = Trade.query.filter_by(user_id=user_id, ticker=ticker).all()
    balance = 0
    for trade in trades:
        if trade.action == 'BUY':
            balance += trade.quantity
        elif trade.action == 'SELL':
            balance -= trade.quantity
    return balance

# Basic Pages ---------------------------------------------------------------------------------------------------------------
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

@app.route('/QTI')
def QTI():
    return render_template('QTI.html')

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
            return (row['Price Bought'] - row['Current Price']) / row['Current Price'] * 100
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

# Run
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)    
