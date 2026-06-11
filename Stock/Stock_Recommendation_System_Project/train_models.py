import os #for creating folders
import yfinance as yf #to take data from yahoo finance
import numpy as np #numerical operations
import pandas as pd  #tabular data processing
from sklearn.ensemble import RandomForestRegressor #for random forest model
from sklearn.preprocessing import MinMaxScaler #normalize numerical values[0,1]
import torch #deep learning framework
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import joblib

# Ensure a stable local directory for storage
os.makedirs('models', exist_ok=True) #to save the trained models in a folder named 'models'

TICKERS = ['AAPL', 'AMZN', 'MSFT', 'GOOGL'] #training models for these 4 stocks

def build_features(df): #adding intelligent features to the raw data for better model performance
    """Calculates custom technical indicators for enhanced ML processing."""
    df['MA_5'] = df['Close'].rolling(window=5).mean() #5-day moving average
    df['MA_20'] = df['Close'].rolling(window=20).mean() #20-day moving average
    df['Daily_Return'] = df['Close'].pct_change() #racCurrent - PeviousPrevious - shows how much stock moved
    df['Target'] = df['Close'].shift(-1) - df['Close'] # Predict the raw difference  # Predict next day's Close
    df.dropna(inplace=True)
    return df

# Define PyTorch LSTM(Long Short-Term Memory) Architecture
class StockLSTM(nn.Module): #to predict the time series prediction of stock prices
    def __init__(self, input_size, hidden_size=50, num_layers=2, output_size=1, dropout=0.2):
        super(StockLSTM, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # Batch_first=True makes tensors (batch, seq, feature)
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=dropout)
        self.fc1 = nn.Linear(hidden_size, 25)
        self.fc2 = nn.Linear(25, output_size)

    def forward(self, x):
        # Initialize hidden and cell states
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        
        # Forward propagate LSTM
        out, _ = self.lstm(x, (h0, c0))
        
        # Extract the output from the last time step
        out = out[:, -1, :]
        out = self.fc1(out)
        out = self.fc2(out)
        return out

def train_ticker_models(ticker):
    print(f"--- Training Models for {ticker} ---")
    data = yf.download(ticker, start="2021-01-01") #download data from yahoo finance for the given ticker starting from Jan 1, 2021
    if data.empty:
        print(f"Failed to fetch data for {ticker}")
        return

    df = build_features(data)
    
    #input features and target variable
    feature_cols = ['Close', 'Open', 'High', 'Low', 'Volume', 'MA_5', 'MA_20', 'Daily_Return']
    X = df[feature_cols].values
    y = df['Target'].values
    
    split = int(len(X) * 0.8) #train-test split of 80-20
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    # --- 1. RANDOM FOREST TRAINING ---
    rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
    rf_model.fit(X_train, y_train) #random forest trainig - past features -> Future price change
    joblib.dump(rf_model, f'models/{ticker}_rf.pkl')
    
    # --- 2. LSTM PREPARATION & TRAINING (PyTorch) ---
    scaler_X = MinMaxScaler(feature_range=(0, 1))
    scaler_y = MinMaxScaler(feature_range=(0, 1))
    
    X_scaled = scaler_X.fit_transform(X)
    y_scaled = scaler_y.fit_transform(y.reshape(-1, 1))
    
    # Form sequence formatting windows (Lookback of 10 periods)
    lookback = 10 #LSTM lookback period - it predicts the next value based on the previous 10 values
    X_lstm, y_lstm = [], []
    for i in range(lookback, len(X_scaled)):
        #Datset COllection
        X_lstm.append(X_scaled[i-lookback:i])
        y_lstm.append(y_scaled[i])
        
    X_lstm, y_lstm = np.array(X_lstm), np.array(y_lstm)
    
    lstm_split = int(len(X_lstm) * 0.8)
    X_train_l, y_train_l = X_lstm[:lstm_split], y_lstm[:lstm_split]
    
    # Create PyTorch DataLoaders
    train_dataset = TensorDataset(torch.tensor(X_train_l, dtype=torch.float32), 
                                  torch.tensor(y_train_l, dtype=torch.float32))
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=False) #Sending data in batches of 32 to the LSTM model for training, shuffle=False to maintain temporal order
    
    # Initialize Engine
    model = StockLSTM(input_size=len(feature_cols))
    criterion = nn.MSELoss() # Mean Squared Error Loss for regression task
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    # PyTorch Training Loop
    model.train()
    for epoch in range(10): #training for 10 epochs - get better performance with more epochs, but it takes more time
        for batch_X, batch_y in train_loader:
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
    
    # Save PyTorch models (using state_dict is standard practice)
    torch.save(model.state_dict(), f'models/{ticker}_lstm.pth') #to save LSTM
    joblib.dump(scaler_X, f'models/{ticker}_scaler_X.pkl')
    joblib.dump(scaler_y, f'models/{ticker}_scaler_y.pkl')
    print(f"Successfully saved variants for {ticker}")

if __name__ == '__main__':
    for ticker in TICKERS:
        train_ticker_models(ticker)
    print("\nAll models calculated and ready.")