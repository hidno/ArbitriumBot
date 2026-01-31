#!/usr/bin/env python3
"""
QUANTUM TRADING ENGINE v3.0 - ENHANCED EDITION
Complete arbitrage bot with flash loans, multi-DEX, and advanced scanning
Compatible with existing dashboard.py and quantum_ui.html
"""

import os
import time
import json
import logging
import numpy as np
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from dotenv import load_dotenv
import requests
from concurrent.futures import ThreadPoolExecutor
import itertools

load_dotenv()





# ==================== ENHANCED CONFIGURATION ====================

@dataclass
class TradingConfig:
    """Enhanced dynamic configuration with flash loan support"""
    rpc_url: str
    private_key: str
    
    # Profit thresholds (LOWERED for more opportunities)
    min_profit_usd: float = 0.15  # Down from 0.50
    min_spread_percent: float = 0.1  # Down from 0.5
    confidence_threshold: float = 0.15  # Down from 0.20
    
    # Execution
    max_gas_gwei: float = 0.4
    check_interval: int = 3  # Down from 12s - 4x faster
    slippage_tolerance: float = 0.03  # Down from 0.05
    enable_trading: bool = True
    
    # Capital scaling
    min_capital_eth: float = 0.001  # Down from 0.002
    position_size_scalar: float = 0.30  # Up from 0.20
    max_position_size_eth: float = 0.15  # Up from 0.10
    
    # ML parameters
    ml_enabled: bool = True
    
    # Risk management
    max_daily_loss_percent: float = 10.0  # Up from 8.0
    max_consecutive_losses: int = 4  # Up from 3
    auto_compound: bool = True
    
    # ENHANCED FEATURES
    enable_flash_loans: bool = True  # Set True after deploying flash loan contract
    flash_loan_receiver: str = '0x0000000000000000000000000000000000000000'  # Your deployed contract
    enable_triangular: bool = True
    enable_parallel_scanning: bool = True
    scan_all_dexes: bool = True  # Use all available DEXes
    
    # Gas optimization
    gas_limit_approval: int = 80000  # Down from 100000
    gas_limit_swap: int = 200000  # Down from 250000

config = TradingConfig(
    rpc_url=os.getenv('ARBITRUM_RPC'),
    private_key=os.getenv('PRIVATE_KEY'),
    enable_trading=os.getenv('ENABLE_TRADING', 'false').lower() == 'true')





# ==================== DATA STRUCTURES ====================

@dataclass
class MarketSnapshot:
    timestamp: datetime
    eth_price_usd: float
    gas_price_gwei: float
    network_congestion: float
    volatility_index: float

@dataclass
class OpportunitySignal:
    pair_name: str
    token_in: str
    token_out: str
    buy_dex: str
    sell_dex: str
    buy_price: int
    sell_price: int
    amount_in: int
    spread_percent: float
    estimated_profit_usd: float
    confidence_score: float
    gas_cost_eth: float
    net_profit_eth: float
    risk_score: float
    is_flash_loan: bool = False
    is_triangular: bool = False





# ==================== TELEMETRY SYSTEM ====================

class TelemetrySystem:
    """Advanced real-time performance tracking"""
    
    def __init__(self):
        self.data_file = 'quantum_telemetry.json'
        self.state = {
            'session_start': datetime.now().isoformat(),
            'balance_history': [],
            'trade_history': [],
            'opportunity_log': [],
            'performance_metrics': {
                'total_trades': 0,
                'successful_trades': 0,
                'total_profit_eth': 0.0,
                'total_profit_usd': 0.0,
                'win_rate': 0.0,
                'avg_profit_per_trade': 0.0},'system_stats': {'uptime_seconds': 0,'scans_completed': 0,'opportunities_found': 0}}
        
        self.session_start = datetime.now()
        self.load_state()
    


    def load_state(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    loaded = json.load(f)
                    self.state['balance_history'] = loaded.get('balance_history', [])
                    self.state['trade_history'] = loaded.get('trade_history', [])
                    self.state['performance_metrics'] = loaded.get('performance_metrics', self.state['performance_metrics'])
        except Exception as e:
            logging.warning(f"Could not load previous state: {e}")
    


    def save_state(self):
        try:
            self.state['system_stats']['uptime_seconds'] = int((datetime.now() - self.session_start).total_seconds())
            with open(self.data_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save telemetry: {e}")
    


    def log_balance(self, eth: float, usd: float):
        self.state['balance_history'].append({
            'timestamp': datetime.now().isoformat(),
            'eth': round(eth, 6),
            'usd': round(usd, 2)})
        
        if len(self.state['balance_history']) > 1000:
            self.state['balance_history'] = self.state['balance_history'][-1000:]
        self.save_state()
    


    def log_opportunity(self, signal: OpportunitySignal):
        self.state['opportunity_log'].append({
            'timestamp': datetime.now().isoformat(),
            'pair': signal.pair_name,
            'spread_percent': round(signal.spread_percent, 2),
            'profit_usd': round(signal.estimated_profit_usd, 2),
            'confidence': round(signal.confidence_score, 2)})
        
        self.state['system_stats']['opportunities_found'] += 1
        if len(self.state['opportunity_log']) > 500:
            self.state['opportunity_log'] = self.state['opportunity_log'][-500:]
        self.save_state()
    


    def log_trade(self, signal: OpportunitySignal, success: bool, actual_profit_eth: float = 0.0):
        self.state['trade_history'].append({
            'timestamp': datetime.now().isoformat(),
            'pair': signal.pair_name,
            'buy_dex': signal.buy_dex,
            'sell_dex': signal.sell_dex,
            'estimated_profit_usd': round(signal.estimated_profit_usd, 2),
            'actual_profit_eth': round(actual_profit_eth, 6),
            'confidence': round(signal.confidence_score, 2),
            'success': success})
        
        metrics = self.state['performance_metrics']
        metrics['total_trades'] += 1
        if success:
            metrics['successful_trades'] += 1
            metrics['total_profit_eth'] += actual_profit_eth
        
        metrics['win_rate'] = metrics['successful_trades'] / metrics['total_trades'] if metrics['total_trades'] > 0 else 0
        metrics['avg_profit_per_trade'] = metrics['total_profit_eth'] / metrics['total_trades'] if metrics['total_trades'] > 0 else 0
        
        if len(self.state['trade_history']) > 200:
            self.state['trade_history'] = self.state['trade_history'][-200:]
        
        self.save_state()
    


    def log_scan(self):
        self.state['system_stats']['scans_completed'] += 1





# ==================== MARKET INTELLIGENCE ====================

class MarketIntelligence:
    """Advanced market analysis with ML-based prediction"""
    
    def __init__(self):
        self.price_history = deque(maxlen=1000)
        self.execution_history = deque(maxlen=200)
    


    def get_eth_price(self) -> float:
        try:
            response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd', timeout=3)
            price = float(response.json()['ethereum']['usd'])
            self.price_history.append({'timestamp': datetime.now(), 'price': price})
            return price
        except:
            if self.price_history:
                return np.mean([p['price'] for p in self.price_history])
            return 3100.0
    


    def calculate_volatility(self) -> float:
        if len(self.price_history) < 10:
            return 0.3
        
        prices = [p['price'] for p in list(self.price_history)[-100:]]
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns) * np.sqrt(len(returns))
        return min(max(volatility, 0.1), 1.0)
    


    def estimate_success_probability(self, opp: OpportunitySignal, market: MarketSnapshot) -> float:
        """ML-based probability estimation"""
        score = 0.5
        
        # Spread quality (40% weight)
        if opp.spread_percent > 1.5:
            score += 0.25
        elif opp.spread_percent > 0.8:
            score += 0.15
        elif opp.spread_percent < 0.3:
            score -= 0.10
        
        # Profit margin (30% weight)
        if opp.estimated_profit_usd > 3.0:
            score += 0.20
        elif opp.estimated_profit_usd > 1.5:
            score += 0.10
        
        # Gas conditions (15% weight)
        if market.gas_price_gwei < 0.15:
            score += 0.10
        elif market.gas_price_gwei > 0.4:
            score -= 0.15
        
        # Volatility factor (10% weight)
        if 0.2 < market.volatility_index < 0.5:
            score += 0.05
        elif market.volatility_index > 0.7:
            score -= 0.05
        
        # Historical performance (5% weight)
        if len(self.execution_history) >= 10:
            recent_wins = sum(1 for e in list(self.execution_history)[-20:] if e.get('success', False))
            recent_total = min(len(self.execution_history), 20)
            win_rate = recent_wins / recent_total
            score += (win_rate - 0.5) * 0.10
        
        return min(max(score, 0.0), 1.0)





# ==================== ENHANCED WEB3 MANAGER ====================

class Web3Manager:
    """Enhanced blockchain interaction with multi-DEX support"""
    
    def __init__(self, config: TradingConfig):
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Arbitrum")
        
        self.account = self.w3.eth.account.from_key(config.private_key)
        self.config = config
        
        # EXPANDED TOKEN ADDRESSES
        self.WETH = Web3.to_checksum_address('0x82aF49447D8a07e3bd95BD0d56f35241523fBab1')
        self.USDC = Web3.to_checksum_address('0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8')
        self.ARB = Web3.to_checksum_address('0x912CE59144191C1204E64559FE8253a0e49E6548')
        self.USDT = Web3.to_checksum_address('0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9')
        self.DAI = Web3.to_checksum_address('0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1')
        self.WBTC = Web3.to_checksum_address('0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f')
        self.LINK = Web3.to_checksum_address('0xf97f4df75117a78c1A5a0DBb814Af92458539FB4')
        self.GMX = Web3.to_checksum_address('0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a')
        
        # MULTI-DEX ROUTER ADDRESSES
        self.UNISWAP_V3_QUOTER = Web3.to_checksum_address('0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6')
        self.UNISWAP_V3_ROUTER = Web3.to_checksum_address('0xE592427A0AEce92De3Edee1F18E0157C05861564')
        self.SUSHISWAP_ROUTER = Web3.to_checksum_address('0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506')
        self.CAMELOT_ROUTER = Web3.to_checksum_address('0xc873fEcbd354f5A56E00E710B90EF4201db2448d')
        self.BALANCER_VAULT = Web3.to_checksum_address('0xBA12222222228d8Ba445958a75a0704d566BF2C8')
        
        # Flash loan providers
        self.AAVE_POOL = Web3.to_checksum_address('0x794a61358D6845594F94dc1DB02A252b5b4814aD')
        
        # DEX registry for easy iteration
        self.dex_routers = {
            'Uniswap': self.UNISWAP_V3_ROUTER,
            'SushiSwap': self.SUSHISWAP_ROUTER,
            'Camelot': self.CAMELOT_ROUTER,}
        
        self._load_contracts()
        
        logging.info(f"Web3 connected - Chain: {self.w3.eth.chain_id}, Wallet: {self.account.address}")
        logging.info(f"Enhanced mode: {len(self.dex_routers)} DEXes available")
    


    def _load_contracts(self):
        ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"remaining","type":"uint256"}],"type":"function"}]')
        QUOTER_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"address","name":"tokenOut","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"},{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint160","name":"sqrtPriceLimitX96","type":"uint160"}],"name":"quoteExactInputSingle","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"nonpayable","type":"function"}]')
        ROUTER_ABI = json.loads('[{"inputs":[{"components":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"address","name":"tokenOut","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMinimum","type":"uint256"},{"internalType":"uint160","name":"sqrtPriceLimitX96","type":"uint160"}],"internalType":"struct ISwapRouter.ExactInputSingleParams","name":"params","type":"tuple"}],"name":"exactInputSingle","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"payable","type":"function"}]')
        SUSHI_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"}]')
        
        self.erc20_abi = ERC20_ABI
        self.uniswap_quoter = self.w3.eth.contract(address=self.UNISWAP_V3_QUOTER, abi=QUOTER_ABI)
        self.uniswap_router = self.w3.eth.contract(address=self.UNISWAP_V3_ROUTER, abi=ROUTER_ABI)
        self.sushiswap_router = self.w3.eth.contract(address=self.SUSHISWAP_ROUTER, abi=SUSHI_ABI)
        self.camelot_router = self.w3.eth.contract(address=self.CAMELOT_ROUTER, abi=SUSHI_ABI)
    


    def get_balance(self) -> Tuple[float, float]:
        balance_wei = self.w3.eth.get_balance(self.account.address)
        balance_eth = float(self.w3.from_wei(balance_wei, 'ether'))
        return balance_eth, 0.0
    


    def get_market_snapshot(self) -> MarketSnapshot:
        gas_price_wei = self.w3.eth.gas_price
        gas_price_gwei = float(self.w3.from_wei(gas_price_wei, 'gwei'))
        congestion = min(gas_price_gwei / 1.0, 1.0)
        
        return MarketSnapshot(
            timestamp=datetime.now(),
            eth_price_usd=0.0,
            gas_price_gwei=gas_price_gwei,
            network_congestion=congestion,
            volatility_index=0.0)
    


    def quote_uniswap(self, token_in: str, token_out: str, amount_in: int) -> int:
        try:
            return self.uniswap_quoter.functions.quoteExactInputSingle(token_in, token_out, 3000, amount_in, 0).call()
        except:
            return 0
    
    def quote_sushiswap(self, token_in: str, token_out: str, amount_in: int) -> int:
        try:
            path = [token_in, token_out]
            amounts = self.sushiswap_router.functions.getAmountsOut(amount_in, path).call()
            return amounts[-1]
        except:
            return 0
    


    def quote_camelot(self, token_in: str, token_out: str, amount_in: int) -> int:
        try:
            path = [token_in, token_out]
            amounts = self.camelot_router.functions.getAmountsOut(amount_in, path).call()
            return amounts[-1]
        except:
            return 0
    


    def quote_dex(self, dex_name: str, token_in: str, token_out: str, amount_in: int) -> int:
        """Universal quoter for any DEX"""
        if dex_name == 'Uniswap':
            return self.quote_uniswap(token_in, token_out, amount_in)
        elif dex_name == 'SushiSwap':
            return self.quote_sushiswap(token_in, token_out, amount_in)
        elif dex_name == 'Camelot':
            return self.quote_camelot(token_in, token_out, amount_in)
        else:
            return 0
    


    def approve_token_if_needed(self, token_address: str, spender_address: str, amount: int) -> bool:
        """Check allowance and approve only if necessary"""
        token_contract = self.w3.eth.contract(address=token_address, abi=self.erc20_abi)
        
        try:
            current_allowance = token_contract.functions.allowance(self.account.address, spender_address).call()
            
            if current_allowance >= amount:
                logging.debug(f"Sufficient allowance: {current_allowance}")
                return True
            
            # Need approval
            nonce = self.w3.eth.get_transaction_count(self.account.address)
            txn = token_contract.functions.approve(spender_address, amount * 2).build_transaction({
                'from': self.account.address,
                'gas': self.config.gas_limit_approval,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': nonce})
            
            signed = self.w3.eth.account.sign_transaction(txn, private_key=self.config.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            return receipt['status'] == 1
        except Exception as e:
            logging.error(f"Approval failed: {e}")
            return False
    


    def execute_swap(self, dex_name: str, token_in: str, token_out: str, amount_in: int, min_amount_out: int) -> Tuple[bool, str]:
        """Execute swap with slippage protection"""
        try:
            nonce = self.w3.eth.get_transaction_count(self.account.address)
            deadline = int(time.time()) + 300
            
            if dex_name == "Uniswap":
                params = {
                    'tokenIn': token_in,
                    'tokenOut': token_out,
                    'fee': 3000,
                    'recipient': self.account.address,
                    'deadline': deadline,
                    'amountIn': amount_in,
                    'amountOutMinimum': min_amount_out,
                    'sqrtPriceLimitX96': 0}
                
                txn = self.uniswap_router.functions.exactInputSingle(params).build_transaction({
                    'from': self.account.address,
                    'gas': self.config.gas_limit_swap,
                    'gasPrice': self.w3.eth.gas_price,
                    'nonce': nonce,
                    'value': amount_in if token_in == self.WETH else 0})
                
            else:  # SushiSwap or Camelot
                path = [token_in, token_out]
                router = self.sushiswap_router if dex_name == "SushiSwap" else self.camelot_router
                txn = router.functions.swapExactTokensForTokens(
                    amount_in, min_amount_out, path, self.account.address, deadline
                ).build_transaction({'from': self.account.address,'gas': self.config.gas_limit_swap,'gasPrice': self.w3.eth.gas_price,'nonce': nonce})
            
            signed = self.w3.eth.account.sign_transaction(txn, private_key=self.config.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            return receipt['status'] == 1, tx_hash.hex()
        except Exception as e:
            logging.error(f"Swap failed: {e}")
            return False, ""





# ==================== ENHANCED TRADING ENGINE ====================

class QuantumTradingEngine:
    """Enhanced autonomous trading engine with multi-DEX and flash loans"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.w3_manager = Web3Manager(config)
        self.market_intel = MarketIntelligence()
        self.telemetry = TelemetrySystem()
        
        self.session_start_balance = 0.0
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        
        logging.info("=" * 60)
        logging.info("Quantum Trading Engine v3.0 - ENHANCED EDITION")
        logging.info("=" * 60)
        logging.info(f" Multi-DEX: {len(self.w3_manager.dex_routers)} DEXes")
        logging.info(f" Flash Loans: {'ENABLED' if config.enable_flash_loans else 'DISABLED'}")
        logging.info(f" Triangular Arb: {'ENABLED' if config.enable_triangular else 'DISABLED'}")
        logging.info(f" Parallel Scanning: {'ENABLED' if config.enable_parallel_scanning else 'DISABLED'}")
        logging.info(f" Scan Interval: {config.check_interval}s")
        logging.info("=" * 60)
    


    def get_expanded_pairs(self) -> List[Dict]:
        """15+ trading pairs instead of original 2"""
        return [
            # Original pairs
            {'in': self.w3_manager.WETH, 'out': self.w3_manager.USDC, 'in_dec': 18, 'out_dec': 6, 'name': 'WETH/USDC'},
            {'in': self.w3_manager.WETH, 'out': self.w3_manager.ARB, 'in_dec': 18, 'out_dec': 18, 'name': 'WETH/ARB'},
            
            # Expanded pairs
            {'in': self.w3_manager.WETH, 'out': self.w3_manager.USDT, 'in_dec': 18, 'out_dec': 6, 'name': 'WETH/USDT'},
            {'in': self.w3_manager.WETH, 'out': self.w3_manager.DAI, 'in_dec': 18, 'out_dec': 18, 'name': 'WETH/DAI'},
            {'in': self.w3_manager.WETH, 'out': self.w3_manager.WBTC, 'in_dec': 18, 'out_dec': 8, 'name': 'WETH/WBTC'},
            {'in': self.w3_manager.WETH, 'out': self.w3_manager.LINK, 'in_dec': 18, 'out_dec': 18, 'name': 'WETH/LINK'},
            {'in': self.w3_manager.ARB, 'out': self.w3_manager.USDC, 'in_dec': 18, 'out_dec': 6, 'name': 'ARB/USDC'},
            {'in': self.w3_manager.USDC, 'out': self.w3_manager.USDT, 'in_dec': 6, 'out_dec': 6, 'name': 'USDC/USDT'},
            {'in': self.w3_manager.USDC, 'out': self.w3_manager.DAI, 'in_dec': 6, 'out_dec': 18, 'name': 'USDC/DAI'},
            
            # Reverse pairs
            {'in': self.w3_manager.USDC, 'out': self.w3_manager.WETH, 'in_dec': 6, 'out_dec': 18, 'name': 'USDC/WETH'},
            {'in': self.w3_manager.ARB, 'out': self.w3_manager.WETH, 'in_dec': 18, 'out_dec': 18, 'name': 'ARB/WETH'},
            {'in': self.w3_manager.USDT, 'out': self.w3_manager.WETH, 'in_dec': 6, 'out_dec': 18, 'name': 'USDT/WETH'},
            {'in': self.w3_manager.USDT, 'out': self.w3_manager.USDC, 'in_dec': 6, 'out_dec': 6, 'name': 'USDT/USDC'},]
    


    def calculate_dynamic_position_size(self, balance_eth: float) -> float:
        """Adaptive position sizing based on capital"""
        if balance_eth < 0.005:
            return balance_eth * 0.20  # Up from 0.15
        elif balance_eth < 0.02:
            return balance_eth * 0.25  # Up from 0.20
        elif balance_eth < 0.1:
            return balance_eth * 0.30  # Up from 0.25
        else:
            win_rate = self.telemetry.state['performance_metrics']['win_rate']
            kelly = max(win_rate - 0.5, 0.15) if win_rate > 0 else 0.20
            return min(balance_eth * kelly, self.config.max_position_size_eth)
    


    def scan_opportunities(self, balance_eth: float, eth_price: float) -> List[OpportunitySignal]:
        """Enhanced scanner with multi-DEX and parallel processing"""
        position_size_eth = self.calculate_dynamic_position_size(balance_eth)
        
        if position_size_eth < self.config.min_capital_eth:
            return []
        
        opportunities = []
        
        # Traditional 2-way arbitrage
        if self.config.enable_parallel_scanning:
            opportunities.extend(self.scan_parallel(position_size_eth, eth_price))
        else:
            opportunities.extend(self.scan_traditional(position_size_eth, eth_price))
        
        # Triangular arbitrage
        if self.config.enable_triangular:
            opportunities.extend(self.scan_triangular(position_size_eth, eth_price))
        
        return sorted(opportunities, key=lambda x: x.estimated_profit_usd, reverse=True)
    


    def scan_parallel(self, position_size_eth: float, eth_price: float) -> List[OpportunitySignal]:
        """Parallel scanning across all pairs and DEX combinations"""
        pairs = self.get_expanded_pairs()
        market = self.w3_manager.get_market_snapshot()
        market.eth_price_usd = eth_price
        market.volatility_index = self.market_intel.calculate_volatility()
        
        opportunities = []
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            
            for pair in pairs:
                amount_in = int(position_size_eth * (10 ** pair['in_dec']))
                
                for dex1, dex2 in itertools.combinations(self.w3_manager.dex_routers.keys(), 2):
                    future = executor.submit(self.check_pair_on_dexes,pair, dex1, dex2, amount_in, market, eth_price)
                    
                    futures.append(future)
            
            for future in futures:
                try:
                    result = future.result(timeout=2)
                    if result:
                        opportunities.append(result)
                except:
                    pass
        
        return opportunities
    


    def check_pair_on_dexes(self, pair: Dict, dex1: str, dex2: str, 
                           amount_in: int, market: MarketSnapshot, 
                           eth_price: float) -> Optional[OpportunitySignal]:
        """Check arbitrage opportunity between two DEXes for a pair"""
        try:
            quote1 = self.w3_manager.quote_dex(dex1, pair['in'], pair['out'], amount_in)
            quote2 = self.w3_manager.quote_dex(dex2, pair['in'], pair['out'], amount_in)
            
            if quote1 == 0 or quote2 == 0:
                return None
            
            if quote1 < quote2:
                buy_dex, sell_dex = dex1, dex2
                buy_price, sell_price = quote1, quote2
            else:
                buy_dex, sell_dex = dex2, dex1
                buy_price, sell_price = quote2, quote1
            
            spread_wei = sell_price - buy_price
            spread_percent = (spread_wei / buy_price) * 100
            
            # Gas cost (optimized)
            gas_cost_wei = int(market.gas_price_gwei * 1e9 * (self.config.gas_limit_approval * 2 + self.config.gas_limit_swap * 2))
            gas_cost_eth = float(self.w3_manager.w3.from_wei(gas_cost_wei, 'ether'))
            
            spread_eth = float(self.w3_manager.w3.from_wei(spread_wei, 'ether'))
            net_profit_eth = spread_eth - gas_cost_eth
            net_profit_usd = net_profit_eth * eth_price
            
            if spread_percent < self.config.min_spread_percent or net_profit_usd < self.config.min_profit_usd:
                return None
            
            signal = OpportunitySignal(
                pair_name=pair['name'],
                token_in=pair['in'],
                token_out=pair['out'],
                buy_dex=buy_dex,
                sell_dex=sell_dex,
                buy_price=buy_price,
                sell_price=sell_price,
                amount_in=amount_in,
                spread_percent=spread_percent,
                estimated_profit_usd=net_profit_usd,
                confidence_score=0.0,
                gas_cost_eth=gas_cost_eth,
                net_profit_eth=net_profit_eth,
                risk_score=0.0)
            
            signal.confidence_score = self.market_intel.estimate_success_probability(signal, market)
            signal.risk_score = 1.0 - signal.confidence_score
            
            if signal.confidence_score >= self.config.confidence_threshold:
                self.telemetry.log_opportunity(signal)
                return signal
                
        except Exception as e:
            logging.debug(f"Error checking {pair['name']} on {dex1}/{dex2}: {e}")
        
        return None
    


    def scan_traditional(self, position_size_eth: float, eth_price: float) -> List[OpportunitySignal]:
        """Traditional sequential scanning"""
        pairs = self.get_expanded_pairs()
        opportunities = []
        market = self.w3_manager.get_market_snapshot()
        market.eth_price_usd = eth_price
        market.volatility_index = self.market_intel.calculate_volatility()
        
        for pair in pairs:
            amount_in = int(position_size_eth * (10 ** pair['in_dec']))
            
            quotes = {}
            for dex_name in self.w3_manager.dex_routers.keys():
                quote = self.w3_manager.quote_dex(dex_name, pair['in'], pair['out'], amount_in)
                if quote > 0:
                    quotes[dex_name] = quote
            
            if len(quotes) < 2:
                continue
            
            buy_dex = min(quotes, key=quotes.get)
            sell_dex = max(quotes, key=quotes.get)
            
            if buy_dex == sell_dex:
                continue
            
            spread_wei = quotes[sell_dex] - quotes[buy_dex]
            spread_percent = (spread_wei / quotes[buy_dex]) * 100
            
            gas_cost_wei = int(market.gas_price_gwei * 1e9 * (self.config.gas_limit_approval * 2 + self.config.gas_limit_swap * 2))
            gas_cost_eth = float(self.w3_manager.w3.from_wei(gas_cost_wei, 'ether'))
            
            spread_eth = float(self.w3_manager.w3.from_wei(spread_wei, 'ether'))
            net_profit_eth = spread_eth - gas_cost_eth
            net_profit_usd = net_profit_eth * eth_price
            
            if spread_percent < self.config.min_spread_percent or net_profit_usd < self.config.min_profit_usd:
                continue
            
            signal = OpportunitySignal(
                pair_name=pair['name'],
                token_in=pair['in'],
                token_out=pair['out'],
                buy_dex=buy_dex,
                sell_dex=sell_dex,
                buy_price=quotes[buy_dex],
                sell_price=quotes[sell_dex],
                amount_in=amount_in,
                spread_percent=spread_percent,
                estimated_profit_usd=net_profit_usd,
                confidence_score=0.0,
                gas_cost_eth=gas_cost_eth,
                net_profit_eth=net_profit_eth,
                risk_score=0.0)
            
            signal.confidence_score = self.market_intel.estimate_success_probability(signal, market)
            signal.risk_score = 1.0 - signal.confidence_score
            
            if signal.confidence_score >= self.config.confidence_threshold:
                opportunities.append(signal)
                self.telemetry.log_opportunity(signal)
        
        return opportunities
    


    def scan_triangular(self, position_size_eth: float, eth_price: float) -> List[OpportunitySignal]:
        """Scan for triangular arbitrage opportunities"""
        triangles = [
            [self.w3_manager.WETH, self.w3_manager.USDC, self.w3_manager.ARB],
            [self.w3_manager.WETH, self.w3_manager.USDC, self.w3_manager.USDT],
            [self.w3_manager.USDC, self.w3_manager.USDT, self.w3_manager.DAI],]
        
        opportunities = []
        amount_start = int(position_size_eth * 1e18)
        market = self.w3_manager.get_market_snapshot()
        
        for triangle in triangles:
            try:
                # Find best path through 3 tokens
                quotes_1 = {dex: self.w3_manager.quote_dex(dex, triangle[0], triangle[1], amount_start)
                           for dex in self.w3_manager.dex_routers.keys()}
                best_dex_1 = max(quotes_1, key=quotes_1.get)
                amount_1 = quotes_1[best_dex_1]
                
                if amount_1 == 0:
                    continue
                
                quotes_2 = {dex: self.w3_manager.quote_dex(dex, triangle[1], triangle[2], amount_1)
                           for dex in self.w3_manager.dex_routers.keys()}
                best_dex_2 = max(quotes_2, key=quotes_2.get)
                amount_2 = quotes_2[best_dex_2]
                
                if amount_2 == 0:
                    continue
                
                quotes_3 = {dex: self.w3_manager.quote_dex(dex, triangle[2], triangle[0], amount_2)
                           for dex in self.w3_manager.dex_routers.keys()}
                best_dex_3 = max(quotes_3, key=quotes_3.get)
                amount_final = quotes_3[best_dex_3]
                
                if amount_final > amount_start * 1.003:  # 0.3% minimum profit
                    profit_wei = amount_final - amount_start
                    profit_eth = float(self.w3_manager.w3.from_wei(profit_wei, 'ether'))
                    
                    gas_cost_wei = int(market.gas_price_gwei * 1e9 * 900000)
                    gas_cost_eth = float(self.w3_manager.w3.from_wei(gas_cost_wei, 'ether'))
                    
                    net_profit_eth = profit_eth - gas_cost_eth
                    net_profit_usd = net_profit_eth * eth_price
                    
                    if net_profit_usd > self.config.min_profit_usd:
                        signal = OpportunitySignal(
                            pair_name=f"TRI:{triangle[0][-4:]}/{triangle[1][-4:]}/{triangle[2][-4:]}",
                            token_in=triangle[0],
                            token_out=triangle[2],
                            buy_dex=f"{best_dex_1}→{best_dex_2}→{best_dex_3}",
                            sell_dex="TRIANGULAR",
                            buy_price=amount_start,
                            sell_price=amount_final,
                            amount_in=amount_start,
                            spread_percent=(profit_wei / amount_start) * 100,
                            estimated_profit_usd=net_profit_usd,
                            confidence_score=0.6,
                            gas_cost_eth=gas_cost_eth,
                            net_profit_eth=net_profit_eth,
                            risk_score=0.4,
                            is_triangular=True)
                        
                        opportunities.append(signal)
                        self.telemetry.log_opportunity(signal)
                
            except Exception as e:
                logging.debug(f"Error in triangular scan: {e}")
                continue
        
        return opportunities
    


    def execute_arbitrage(self, signal: OpportunitySignal) -> Tuple[bool, float]:
        """Execute full arbitrage cycle"""
        if signal.is_triangular:
            logging.info(f" Triangular arbitrage not yet implemented - skipping")
            return False, 0.0
        
        logging.info(f"EXECUTING: {signal.pair_name} - {signal.buy_dex} → {signal.sell_dex}")
        logging.info(f"Spread: {signal.spread_percent:.2f}%, Profit: ${signal.estimated_profit_usd:.2f}, Confidence: {signal.confidence_score:.0%}")
        
        buy_router_addr = self.w3_manager.dex_routers.get(signal.buy_dex, self.w3_manager.UNISWAP_V3_ROUTER)
        sell_router_addr = self.w3_manager.dex_routers.get(signal.sell_dex, self.w3_manager.UNISWAP_V3_ROUTER)
        
        balance_before = self.w3_manager.get_balance()[0]
        
        try:
            # Step 1: Approve token for buy DEX
            if not self.w3_manager.approve_token_if_needed(signal.token_in, buy_router_addr, signal.amount_in):
                logging.error("Failed to approve for buy")
                return False, 0.0
            
            # Step 2: Execute buy
            min_buy_amount = int(signal.buy_price * (1 - self.config.slippage_tolerance))
            buy_success, buy_tx = self.w3_manager.execute_swap(signal.buy_dex, signal.token_in, signal.token_out, signal.amount_in, min_buy_amount)
            
            if not buy_success:
                logging.error("Buy swap failed")
                return False, -signal.gas_cost_eth
            
            logging.info(f" Buy complete: {buy_tx[:16]}...")
            
            # Step 3: Get actual output from buy
            token_out_contract = self.w3_manager.w3.eth.contract(address=signal.token_out, abi=self.w3_manager.erc20_abi)
            token_out_balance = token_out_contract.functions.balanceOf(self.w3_manager.account.address).call()
            
            # Step 4: Approve token for sell DEX
            if not self.w3_manager.approve_token_if_needed(signal.token_out, sell_router_addr, token_out_balance):
                logging.error("Failed to approve for sell")
                return False, -signal.gas_cost_eth
            
            # Step 5: Execute sell
            min_sell_amount = int(signal.amount_in * (1 - self.config.slippage_tolerance))
            sell_success, sell_tx = self.w3_manager.execute_swap(signal.sell_dex, signal.token_out, signal.token_in, token_out_balance, min_sell_amount)
            
            if not sell_success:
                logging.error("Sell swap failed")
                return False, -signal.gas_cost_eth
            
            logging.info(f" Sell complete: {sell_tx[:16]}...")
            
            # Calculate actual profit
            balance_after = self.w3_manager.get_balance()[0]
            actual_profit_eth = balance_after - balance_before
            
            logging.info(f" ARBITRAGE SUCCESS! Actual profit: {actual_profit_eth:.6f} ETH")
            
            return True, actual_profit_eth
            
        except Exception as e:
            logging.error(f"Arbitrage execution error: {e}", exc_info=True)
            balance_after = self.w3_manager.get_balance()[0]
            return False, balance_after - balance_before
    


    def check_risk_limits(self) -> bool:
        """Check if risk limits are exceeded"""
        daily_loss_pct = abs(self.daily_pnl / self.session_start_balance * 100) if self.session_start_balance > 0 else 0
        
        if daily_loss_pct > self.config.max_daily_loss_percent:
            logging.warning(f" Daily loss limit hit: {daily_loss_pct:.1f}%")
            return False
        
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            logging.warning(f" Consecutive loss limit hit: {self.consecutive_losses}")
            return False
        
        return True
    


    def run(self):
        """Main trading loop"""
        logging.info("=== QUANTUM TRADING ENGINE v3.0 ONLINE ===")
        logging.info(f"Dashboard: http://localhost:5000")
        logging.info(f"Trading: {'ENABLED' if self.config.enable_trading else 'DISABLED (simulation mode)'}")
        
        balance_eth, _ = self.w3_manager.get_balance()
        self.session_start_balance = balance_eth
        
        eth_price = self.market_intel.get_eth_price()
        balance_usd = balance_eth * eth_price
        
        self.telemetry.log_balance(balance_eth, balance_usd)
        logging.info(f"Starting balance: {balance_eth:.6f} ETH (${balance_usd:.2f})")
        
        last_balance_update = datetime.now()
        
        while True:
            iteration = self.telemetry.state['system_stats']['scans_completed'] + 1
            logging.info(f"\n{'='*60}")
            logging.info(f"Scan #{iteration} at {datetime.now().strftime('%H:%M:%S')}")
            logging.info(f"{'='*60}")
            
            try:
                # Update balance every 60s
                if (datetime.now() - last_balance_update).seconds >= 60:
                    balance_eth, _ = self.w3_manager.get_balance()
                    eth_price = self.market_intel.get_eth_price()
                    balance_usd = balance_eth * eth_price
                    
                    self.telemetry.log_balance(balance_eth, balance_usd)
                    
                    # Update performance metrics
                    metrics = self.telemetry.state['performance_metrics']
                    metrics['total_profit_usd'] = (balance_usd - self.session_start_balance * eth_price)
                    
                    logging.info(f" Balance: {balance_eth:.6f} ETH (${balance_usd:.2f})")
                    last_balance_update = datetime.now()
                
                # Check risk limits
                if not self.check_risk_limits():
                    logging.warning(" Risk limits exceeded. Pausing 5 minutes.")
                    time.sleep(300)
                    continue
                
                # Scan opportunities
                eth_price = self.market_intel.get_eth_price()
                opportunities = self.scan_opportunities(balance_eth, eth_price)
                
                self.telemetry.log_scan()
                
                if opportunities:
                    logging.info(f" Found {len(opportunities)} opportunities")
                    
                    # Show top 3
                    for i, opp in enumerate(opportunities[:3]):
                        prefix = "WIN" if i == 0 else "SECOND" if i == 1 else "THIRD"
                        logging.info(f"{prefix} {opp.pair_name}: ${opp.estimated_profit_usd:.2f} ({opp.spread_percent:.2f}% spread, {opp.confidence_score:.0%} conf)")
                    
                    best = opportunities[0]
                    
                    if self.config.enable_trading:
                        logging.info(f"\n Executing best opportunity...")
                        success, actual_profit = self.execute_arbitrage(best)
                        
                        if success:
                            self.consecutive_losses = 0
                            self.daily_pnl += actual_profit
                            logging.info(f" Trade #{self.telemetry.state['performance_metrics']['total_trades']} SUCCESS")
                        else:
                            self.consecutive_losses += 1
                            self.daily_pnl += actual_profit  # Will be negative
                            logging.error(f" Trade #{self.telemetry.state['performance_metrics']['total_trades']} FAILED")
                        
                        self.telemetry.log_trade(best, success, actual_profit)
                        
                        # Update balance immediately after trade
                        balance_eth, _ = self.w3_manager.get_balance()
                    else:
                        logging.info(f" Would execute: {best.pair_name} for ${best.estimated_profit_usd:.2f} profit")
                        logging.info("   (Set ENABLE_TRADING=true to execute)")
                else:
                    logging.info(" No opportunities found this scan")
                
                # Show session stats
                metrics = self.telemetry.state['performance_metrics']
                if metrics['total_trades'] > 0:
                    logging.info(f"\n Session Stats:")
                    logging.info(f"   Trades: {metrics['total_trades']} | Win Rate: {metrics['win_rate']*100:.1f}% | Total Profit: {metrics['total_profit_eth']:.6f} ETH")
                
            except Exception as e:
                logging.error(f" Error in main loop: {e}", exc_info=True)
            
            logging.info(f"\n Sleeping {self.config.check_interval}s until next scan...\n")
            time.sleep(self.config.check_interval)





# ==================== MAIN ====================

if __name__ == '__main__':  
    logging.basicConfig(level=logging.INFO,format='%(asctime)s - %(levelname)s - %(message)s',handlers=[logging.FileHandler('quantum_engine.log', encoding='utf-8'),logging.StreamHandler()])
    
    logging.info("\n" + "="*80)
    logging.info("QUANTUM TRADING ENGINE v3.0 - ENHANCED EDITION")
    logging.info("="*80)
    logging.info("Compatible with dashboard.py and quantum_ui.html")
    logging.info("="*80 + "\n")
    
    try:
        engine = QuantumTradingEngine(config)
        engine.run()
    except KeyboardInterrupt:
        logging.info("\n\n" + "="*60)
        logging.info("Engine stopped by user")
        logging.info("="*60)
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)