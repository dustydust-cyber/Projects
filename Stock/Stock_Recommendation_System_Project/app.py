from flask import Flask, render_template, request, jsonify
import yfinance as yf
import numpy as np
import pandas as pd
import joblib
import torch
import torch.nn as nn
import plotly.graph_objs as go
import plotly.io as pio

app = Flask(__name__)

# Mock performance metrics derived during testing structures
ACCURACY_METRICS = {
    'AAPL': {'rf_rmse': 2.14, 'lstm_rmse': 1.89},
    'AMZN': {'rf_rmse': 3.02, 'lstm_rmse': 2.45},
    'MSFT': {'rf_rmse': 4.12, 'lstm_rmse': 3.67},
    'GOOGL': {'rf_rmse': 2.89, 'lstm_rmse': 2.12}
}

# Duplicate the model architecture to load the PyTorch state dict
class StockLSTM(nn.Module):
    def __init__(self, input_size, hidden_size=50, num_layers=2, output_size=1, dropout=0.2):
        super(StockLSTM, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=dropout)
        self.fc1 = nn.Linear(hidden_size, 25)
        self.fc2 = nn.Linear(25, output_size)

    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        out, _ = self.lstm(x, (h0, c0))
        out = out[:, -1, :]
        out = self.fc1(out)
        out = self.fc2(out)
        return out

def get_live_data(ticker):
    """Fetches trailing periods necessary to feed feature windows dynamically."""
    df = yf.download(ticker, period="6mo")
    
    # FIXED: Indented this block correctly
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df['MA_5'] = df['Close'].rolling(window=5).mean()
    df['MA_20'] = df['Close'].rolling(window=20).mean()
    df['Daily_Return'] = df['Close'].pct_change()
    return df.dropna()

def generate_recommendation(current, pred_rf, pred_lstm):
    """Generates explicit trade indicators using an ensemble directional split."""
    avg_pred = (pred_rf + pred_lstm) / 2
    pct_change = ((avg_pred - current) / current) * 100
    
    if pct_change > 1.5:
        return "Strong Buy", "success", f"Predicted upswing of {pct_change:.2f}% expected over next session."
    elif pct_change > 0.4:
        return "Buy", "primary", f"Modest continuous gains of {pct_change:.2f}% projected."
    elif pct_change < -1.5:
        return "Sell", "danger", f"Downward correction of {pct_change:.2f}% calculated."
    else:
        return "Hold", "warning", f"Consolidating value frame change localized at {pct_change:.2f}%."

@app.route('/')
def index():
    return render_template('index.html', tickers=ACCURACY_METRICS.keys())

@app.route('/predict', methods=['POST'])
def predict():
    ticker = request.form.get('ticker')
    df = get_live_data(ticker)
    
    if df.empty:
        return jsonify({'error': 'Failed to capture real-time pricing indicators.'}), 400
    
    # FIXED: Indented print statements so they belong to the function
    print(df.columns)
    print(type(df['Close']))
    print(df['Close'].tail())

    # FIXED: Restored safeguard to prevent Series float-cast crashes
    close_entry = df['Close'].iloc[-1]
    if isinstance(close_entry, pd.Series):
        close_entry = close_entry.squeeze()
    current_price = float(close_entry)
    
    feature_cols = ['Close', 'Open', 'High', 'Low', 'Volume', 'MA_5', 'MA_20', 'Daily_Return']
    latest_features = df[feature_cols].iloc[-1].values.reshape(1, -1)
    
    # --- Execute Random Forest Inference ---
    rf_model = joblib.load(f'models/{ticker}_rf.pkl')
    pred_rf = float(rf_model.predict(latest_features)[0])
    
    # --- Execute LSTM Inference (PyTorch) ---
    scaler_X = joblib.load(f'models/{ticker}_scaler_X.pkl')
    scaler_y = joblib.load(f'models/{ticker}_scaler_y.pkl')
    
    # Initialize the architecture & load the saved weights mapping
    lstm_model = StockLSTM(input_size=len(feature_cols))
    lstm_model.load_state_dict(torch.load(f'models/{ticker}_lstm.pth', weights_only=True))
    lstm_model.eval() # Set model to evaluation mode
    
    # Gather historical 10-period context lookback matrix
    seq_features = df[feature_cols].iloc[-10:].values
    seq_scaled = scaler_X.transform(seq_features).reshape(1, 10, len(feature_cols))
    
    # Perform forward pass and extract
    with torch.no_grad():
        seq_tensor = torch.tensor(seq_scaled, dtype=torch.float32) # Explicitly CPU
        pred_lstm_scaled = lstm_model(seq_tensor).numpy()
        
    pred_lstm = float(scaler_y.inverse_transform(pred_lstm_scaled)[0][0])
    
    # Evaluate Trade Output Status
    action, badge_color, logic_text = generate_recommendation(current_price, pred_rf, pred_lstm)
    
    
    # --- Plotly Candlestick Synthesis ---
    # We use .tolist() and .strftime to ensure 100% clean JSON serialization for JavaScript
    fig = go.Figure(data=[go.Candlestick(
        x=df.index[-60:].strftime('%Y-%m-%d').tolist(),  # Force clean date strings
        open=df['Open'].iloc[-60:].squeeze().tolist(),   # Force native Python lists
        high=df['High'].iloc[-60:].squeeze().tolist(),
        low=df['Low'].iloc[-60:].squeeze().tolist(),
        close=df['Close'].iloc[-60:].squeeze().tolist(),
        name='Market Price'
    )])
    
    fig.update_layout(
        title=f'{ticker} Technical Chart (Trailing 60 Trading Days)',
        template='plotly_dark',
        xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    graph_json = pio.to_json(fig)
    
    return jsonify({
        'current_price': f"${current_price:.2f}",
        'pred_rf': f"${pred_rf:.2f}",
        'pred_lstm': f"${pred_lstm:.2f}",
        'rf_rmse': f"{ACCURACY_METRICS[ticker]['rf_rmse']:.2f}",
        'lstm_rmse': f"{ACCURACY_METRICS[ticker]['lstm_rmse']:.2f}",
        'action': action,
        'badge_color': badge_color,
        'logic_text': logic_text,
        'graph': graph_json
    })

if __name__ == '__main__':
    app.run(debug=True)

