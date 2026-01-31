#!/usr/bin/env python3
"""
Dashboard Backend
Serves real-time telemetry data via REST API
"""

from flask import Flask, jsonify, send_file
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)





@app.route('/')
def index():
    """Serve the UI"""
    return send_file('quantum_ui.html')





@app.route('/api/data')
def get_data():
    """Primary data endpoint with error handling"""
    try:
        if not os.path.exists('quantum_telemetry.json'):
            return jsonify(create_empty_response())
        
        with open('quantum_telemetry.json', 'r') as f:
            content = f.read().strip()

            if not content:
                return jsonify(create_empty_response())
            data = json.loads(content)
        




        # Calculate growth metrics
        if data.get('balance_history') and len(data['balance_history']) > 0:
            current = data['balance_history'][-1]
            start = data['balance_history'][0]
            
            current_usd = current.get('usd', 0)
            start_usd = start.get('usd', 1)
            




            # Hourly growth
            one_hour_ago = datetime.now() - timedelta(hours=1)
            recent = [b for b in data['balance_history'] if datetime.fromisoformat(b['timestamp']) > one_hour_ago]
            
            hourly_growth = 0.0
            if recent:
                hour_start = recent[0].get('usd', current_usd)
                if hour_start > 0:
                    hourly_growth = ((current_usd - hour_start) / hour_start) * 100
            
            # Total growth
            total_growth = ((current_usd - start_usd) / start_usd) * 100 if start_usd > 0 else 0
            data['growth'] = {'current_usd': round(current_usd, 2),'start_usd': round(start_usd, 2),'hourly_percent': round(hourly_growth, 2),'total_percent': round(total_growth, 2),'profit_usd': round(current_usd - start_usd, 2)}
            
        else:
            data['growth'] = create_empty_growth()
        
        return jsonify(data)
        
    except Exception as e:
        print(f"API error: {e}")
        return jsonify(create_empty_response())





def create_empty_response():
    """Create empty response structure"""
    return {'balance_history': [],'trade_history': [],'opportunity_log': [],'performance_metrics': {'total_trades': 0,'successful_trades': 0,'win_rate': 0.0,'total_profit_eth': 0.0,'avg_profit_per_trade': 0.0},'system_stats': {'uptime_seconds': 0,'scans_completed': 0,'opportunities_found': 0},'growth': create_empty_growth()}

def create_empty_growth():
    return {'current_usd': 0.0,'start_usd': 0.0,'hourly_percent': 0.0,'total_percent': 0.0,'profit_usd': 0.0}

if __name__ == '__main__':
    print("Quantum Dashboard starting on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
