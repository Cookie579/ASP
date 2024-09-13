# downloader.py

import yfinance as yf
import pandas as pd
import io, csv, json, sys, os

json_file_path = os.path.join('static', 'temp', 'temp.json')
os.makedirs(os.path.dirname(json_file_path), exist_ok=True)

def convert_float(item):
    if isinstance(item, list):
        return [convert_float(sub_item) for sub_item in item]
    
    else:
        try:
            return round(float(item), 2)
        
        except ValueError:
            return item

def download_data(ticker):
    # Downloading data
    
    code = str(ticker)

    data = yf.download(code, interval='1d', period='max')
    data = pd.DataFrame(data)

    data['Datetime'] = data.index
    data['Datetime'] = pd.to_datetime(data['Datetime'])
    data['Datetime'] = data['Datetime'].astype('int64')
    data['Datetime'] = data['Datetime'].div(10**6)

    data = data[['Datetime', 'Open', 'High', 'Low', 'Close', 'Volume']]
    data.index = data['Datetime']
    data = data.drop('Datetime', axis=1)
    data = data.astype(float)
    data = data.to_csv()

    rows = []
    count = 0

    with io.StringIO(data) as file:
        csv_reader = csv.reader(file)

        for row in csv_reader:
            if count == 0:
                count += 1
                continue

            else:
                rows.append(row)

    data = rows
    data = convert_float(data)
    data = json.dumps(data)

    with open(json_file_path, 'w') as json_file:
        json.dump(data, json_file)

    fp = 'static/temp/temp.json'

    with open(fp, 'r') as file:
        content = file.read()
    
    mc = content[1:-1]

    with open(fp, 'w') as file:
        file.write(mc)

    return data

if __name__ == "__main__":
    ticker = sys.argv[1]
    print(download_data(ticker))
