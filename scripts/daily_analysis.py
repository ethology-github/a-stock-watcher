#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股守望者 - 每日行情分析脚本
支持三种模式：盘前(pre)、盘中(mid)、盘后(post)
"""

import sys
import json
import warnings
from datetime import datetime, date
from pathlib import Path

warnings.filterwarnings('ignore')

# 尝试导入mootdx
try:
    from mootdx.quotes import Quotes
    MOOTDX_AVAILABLE = True
except ImportError:
    MOOTDX_AVAILABLE = False

# 尝试导入akshare
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False


class StockAnalyzer:
    """行情分析器"""
    
    def __init__(self):
        self.server = ('124.70.199.56', 7709)
        self.results = {}
        
    def get_index_data(self, symbol='000001'):
        """获取指数数据"""
        if not MOOTDX_AVAILABLE:
            return None
        try:
            client = Quotes.factory(market='std', server=self.server, timeout=10)
            df = client.index(symbol=symbol, frequency=9, offset=5)
            client.close()
            if df is not None and len(df) > 0:
                return df.tail(5)
            return None
        except Exception as e:
            print(f"mootdx获取失败: {e}")
            return None
    
    def get_stock_bars(self, symbol, offset=5):
        """获取个股K线"""
        if not MOOTDX_AVAILABLE:
            return None
        try:
            client = Quotes.factory(market='std', server=self.server, timeout=10)
            df = client.bars(symbol=symbol, frequency=9, offset=offset)
            client.close()
            if df is not None and len(df) > 0:
                return df
            return None
        except Exception as e:
            print(f"获取{symbol}失败: {e}")
            return None
    
    def get_realtime_quote(self, symbol):
        """获取实时行情"""
        if not MOOTDX_AVAILABLE:
            return None
        try:
            client = Quotes.factory(market='std', server=self.server, timeout=10)
            df = client.quotes(symbol=[symbol])
            client.close()
            if df is not None and len(df) > 0:
                return df.iloc[-1]
            return None
        except Exception as e:
            print(f"获取{symbol}实时行情失败: {e}")
            return None
    
    def get_zt_pool(self, trade_date=None):
        """获取涨跌停池"""
        if not AKSHARE_AVAILABLE:
            return {'zt': [], 'dt': [], 'zt_count': 0, 'dt_count': 0}
        try:
            if trade_date is None:
                trade_date = date.today().strftime('%Y%m%d')
            df = ak.stock_zt_pool_em(date=trade_date)
            if df is not None and len(df) > 0:
                # 尝试找到涨幅列
                for col in df.columns:
                    if '涨' in col and '幅' in col:
                        return {
                            'zt': df[df[col] >= 9.9].head(10).to_dict('records'),
                            'dt': df[df[col] <= -9.9].head(10).to_dict('records'),
                            'zt_count': len(df[df[col] >= 9.9]),
                            'dt_count': len(df[df[col] <= -9.9])
                        }
                return {'zt': [], 'dt': [], 'zt_count': 0, 'dt_count': 0}
            return {'zt': [], 'dt': [], 'zt_count': 0, 'dt_count': 0}
        except Exception as e:
            print(f"获取涨跌停池失败: {e}")
            return {'zt': [], 'dt': [], 'zt_count': 0, 'dt_count': 0}
    
    def calculate_ma(self, df, periods=[5, 10, 20]):
        """计算均线"""
        if df is None or 'close' not in df.columns:
            return {}
        result = {}
        for p in periods:
            if len(df) >= p:
                result[f'ma{p}'] = round(df['close'].tail(p).mean(), 3)
        return result
    
    def analyze_stock(self, symbol, name):
        """分析单只股票"""
        result = {
            'name': name,
            'symbol': symbol,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': 'mootdx'
        }
        
        df = self.get_stock_bars(symbol, offset=20)
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            
            result['price'] = round(float(latest['close']), 3)
            result['change'] = round(float(latest['close'] - prev['close']), 3)
            result['change_pct'] = round((latest['close'] - prev['close']) / prev['close'] * 100, 2) if prev['close'] != 0 else 0
            result['volume'] = int(latest['vol']) if 'vol' in latest else 0
            result['high'] = round(float(latest['high']), 3)
            result['low'] = round(float(latest['low']), 3)
            result['open'] = round(float(latest['open']), 3)
            result['prev_close'] = round(float(prev['close']), 3)
            
            ma = self.calculate_ma(df)
            result.update(ma)
            
            # 趋势判断
            if 'ma5' in result and 'ma20' in result:
                if result['price'] > result['ma20']:
                    result['trend'] = '上升'
                elif result['price'] < result['ma20']:
                    result['trend'] = '下降'
                else:
                    result['trend'] = '震荡'
            else:
                result['trend'] = '数据不足'
                
        else:
            result['error'] = '获取数据失败'
            
        return result


class Portfolio:
    """持仓管理器"""
    
    def __init__(self, state_file=None):
        if state_file is None:
            state_file = Path(__file__).parent.parent / 'portfolio' / 'portfolio_state.json'
        self.state_file = Path(state_file)
        self.state = self.load_state()
        
    def load_state(self):
        """加载持仓状态"""
        if self.state_file.exists():
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'name': 'A股守望者实盘账户',
            'capital': 1000000,
            'start_date': date.today().strftime('%Y-%m-%d'),
            'positions': {},
            'cash': 1000000,
            'total_value': 1000000,
            'total_profit': 0,
            'total_profit_pct': 0
        }
    
    def save_state(self):
        """保存持仓状态"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def update_positions(self, analyzer):
        """更新持仓行情"""
        for pos_id, pos in self.state['positions'].items():
            symbol = pos['symbol']
            quote = analyzer.get_realtime_quote(symbol)
            if quote is not None:
                pos['current_price'] = round(float(quote.get('close', 0)), 3)
                pos['current_value'] = round(pos['current_price'] * pos['shares'], 2)
                pos['profit'] = round(pos['current_value'] - pos['cost'], 2)
                pos['profit_pct'] = round(pos['profit'] / pos['cost'] * 100, 2) if pos['cost'] > 0 else 0
                
        # 重新计算总市值
        positions_value = sum(pos['current_value'] for pos in self.state['positions'].values())
        self.state['cash'] = round(self.state['cash'], 2)
        self.state['total_value'] = round(positions_value + self.state['cash'], 2)
        self.state['total_profit'] = round(self.state['total_value'] - self.state['capital'], 2)
        self.state['total_profit_pct'] = round(self.state['total_profit'] / self.state['capital'] * 100, 2)
        
        self.save_state()
        return self.state
    
    def add_position(self, symbol, name, price, shares, stop_loss, target1, target2):
        """添加持仓"""
        cost = round(price * shares, 2)
        if cost > self.state['cash']:
            return {'error': f'资金不足，需要{cost}元，当前可用{self.state["cash"]}元'}
        
        pos_id = f"{symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.state['positions'][pos_id] = {
            'symbol': symbol,
            'name': name,
            'buy_price': price,
            'shares': shares,
            'cost': cost,
            'stop_loss': stop_loss,
            'target1': target1,
            'target2': target2,
            'buy_date': date.today().strftime('%Y-%m-%d'),
            'current_price': price,
            'current_value': cost,
            'profit': 0,
            'profit_pct': 0,
            'status': '持仓中'
        }
        
        self.state['cash'] = round(self.state['cash'] - cost, 2)
        self.save_state()
        
        return {'success': True, 'position_id': pos_id}
    
    def close_position(self, pos_id, close_price, reason=''):
        """平仓"""
        if pos_id not in self.state['positions']:
            return {'error': '持仓不存在'}
        
        pos = self.state['positions'][pos_id]
        close_value = round(close_price * pos['shares'], 2)
        profit = round(close_value - pos['cost'], 2)
        
        # 记录到历史
        history_entry = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'action': '卖出' if profit >= 0 else '止损',
            'symbol': pos['symbol'],
            'name': pos['name'],
            'buy_price': pos['buy_price'],
            'close_price': close_price,
            'shares': pos['shares'],
            'profit': profit,
            'profit_pct': round(profit / pos['cost'] * 100, 2),
            'reason': reason
        }
        
        if 'history' not in self.state:
            self.state['history'] = []
        self.state['history'].append(history_entry)
        
        # 返还资金
        self.state['cash'] = round(self.state['cash'] + close_value, 2)
        del self.state['positions'][pos_id]
        
        # 重新计算
        positions_value = sum(p['current_value'] for p in self.state['positions'].values())
        self.state['total_value'] = round(positions_value + self.state['cash'], 2)
        self.state['total_profit'] = round(self.state['total_value'] - self.state['capital'], 2)
        self.state['total_profit_pct'] = round(self.state['total_profit'] / self.state['capital'] * 100, 2)
        
        self.save_state()
        return {'success': True, 'profit': profit, 'history_entry': history_entry}


def pre_market_report():
    """盘前分析报告"""
    print("=" * 80)
    print("【A股守望者 · 盘前分析】" + datetime.now().strftime('%Y年%m月%d日 %H:%M'))
    print("=" * 80)
    
    analyzer = StockAnalyzer()
    
    # 获取主要指数
    print("\n【主要指数】")
    indices = [
        ('000001', '上证指数'),
        ('399001', '深证成指'),
        ('399006', '创业板指'),
        ('000688', '科创50')
    ]
    
    for symbol, name in indices:
        df = analyzer.get_index_data(symbol)
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            change = latest['close'] - prev['close']
            change_pct = change / prev['close'] * 100 if prev['close'] != 0 else 0
            print(f"  {name}: {latest['close']:.3f} {'+' if change >= 0 else ''}{change:.3f} ({'+' if change_pct >= 0 else ''}{change_pct:.2f}%)")
    
    # 昨日涨跌停情况
    print("\n【昨日涨跌停】")
    zt_data = analyzer.get_zt_pool()
    print(f"  涨停: {len(zt_data.get('zt', []))} 只")
    print(f"  跌停: {len(zt_data.get('dt', []))} 只")
    
    print("\n【操作建议】")
    print("  建议仓位：待大盘确认")
    print("  关注标的：待今日开盘后确认")
    print("  注意事项：")
    print("    1. 等开盘后确认趋势再做决策")
    print("    2. 不要在集合竞价时追高")
    print("    3. 保留足够的子弹")
    
    print("\n" + "=" * 80)
    return True


def mid_market_report():
    """盘中分析报告"""
    print("=" * 80)
    print("【A股守望者 · 盘中分析】" + datetime.now().strftime('%Y年%m月%d日 %H:%M'))
    print("=" * 80)
    
    analyzer = StockAnalyzer()
    portfolio = Portfolio()
    
    # 更新持仓行情
    state = portfolio.update_positions(analyzer)
    
    print(f"\n【账户状态】")
    print(f"  初始资金: {state['capital']:,.0f} 元")
    print(f"  当前市值: {state['total_value']:,.2f} 元")
    print(f"  持仓盈亏: {'+' if state['total_profit'] >= 0 else ''}{state['total_profit']:,.2f} 元 ({'+' if state['total_profit_pct'] >= 0 else ''}{state['total_profit_pct']:.2f}%)")
    print(f"  可用现金: {state['cash']:,.2f} 元")
    print(f"  持仓市值: {state['total_value'] - state['cash']:,.2f} 元")
    print(f"  仓位: {(state['total_value'] - state['cash']) / state['total_value'] * 100:.1f}%")
    
    if state['positions']:
        print("\n【持仓明细】")
        for pos_id, pos in state['positions'].items():
            trend_icon = '📈' if pos['profit_pct'] >= 0 else '📉'
            stop_icon = '⚠️' if pos['current_price'] <= pos['stop_loss'] else ''
            print(f"  {trend_icon} {pos['name']}({pos['symbol']})")
            print(f"     买入价: {pos['buy_price']} | 当前: {pos['current_price']} | 盈亏: {'+' if pos['profit_pct'] >= 0 else ''}{pos['profit_pct']:.2f}% {stop_icon}")
            print(f"     止损: {pos['stop_loss']} | 目标1: {pos['target1']} | 目标2: {pos['target2']}")
    else:
        print("\n【持仓明细】暂无持仓")
    
    # 指数
    print("\n【主要指数】")
    indices = [
        ('000001', '上证指数'),
        ('399006', '创业板指')
    ]
    
    for symbol, name in indices:
        quote = analyzer.get_realtime_quote(symbol)
        if quote is not None:
            price = quote.get('close', 0)
            prev_close = quote.get('prev_close', price)
            change = price - prev_close
            change_pct = change / prev_close * 100 if prev_close != 0 else 0
            print(f"  {name}: {price:.3f} {'+' if change >= 0 else ''}{change:.3f} ({'+' if change_pct >= 0 else ''}{change_pct:.2f}%)")
    
    print("\n【盘中提示】")
    if state['positions']:
        for pos_id, pos in state['positions'].items():
            if pos['current_price'] <= pos['stop_loss']:
                print(f"  ⚠️ 止损警告: {pos['name']} 当前价{pos['current_price']}已达到止损价{pos['stop_loss']}")
            elif pos['current_price'] >= pos['target2']:
                print(f"  🎯 目标达成: {pos['name']} 已达到第二目标{pos['target2']}，建议减仓")
            elif pos['current_price'] >= pos['target1']:
                print(f"  🎯 第一目标: {pos['name']} 已达到第一目标{pos['target1']}，可考虑减仓1/3")
    else:
        print("  暂无持仓，等待机会")
    
    print("\n" + "=" * 80)
    return True


def post_market_report():
    """盘后复盘报告"""
    print("=" * 80)
    print("【A股守望者 · 盘后复盘】" + datetime.now().strftime('%Y年%m月%d日'))
    print("=" * 80)
    
    analyzer = StockAnalyzer()
    portfolio = Portfolio()
    
    # 更新持仓行情（使用收盘价）
    state = portfolio.update_positions(analyzer)
    
    print(f"\n【账户统计】")
    print(f"  初始资金: {state['capital']:,.0f} 元")
    print(f"  当前总市值: {state['total_value']:,.2f} 元")
    print(f"  今日盈亏: {'+' if state['total_profit'] >= 0 else ''}{state['total_profit']:,.2f} 元 ({'+' if state['total_profit_pct'] >= 0 else ''}{state['total_profit_pct']:.2f}%)")
    print(f"  可用现金: {state['cash']:,.2f} 元")
    print(f"  持仓市值: {state['total_value'] - state['cash']:,.2f} 元")
    print(f"  当前仓位: {(state['total_value'] - state['cash']) / state['total_value'] * 100:.1f}%")
    
    if state['positions']:
        print("\n【持仓明细】")
        for pos_id, pos in state['positions'].items():
            profit_icon = '✅' if pos['profit_pct'] >= 0 else '❌'
            stop_flag = '⚠️止损' if pos['current_price'] <= pos['stop_loss'] else ''
            print(f"  {profit_icon} {pos['name']}({pos['symbol']}) {stop_flag}")
            print(f"     买入: {pos['buy_price']} | 现价: {pos['current_price']} | 盈亏: {'+' if pos['profit'] >= 0 else ''}{pos['profit']:.2f}元 ({'+' if pos['profit_pct'] >= 0 else ''}{pos['profit_pct']:.2f}%)")
            print(f"     止损: {pos['stop_loss']} | 目标1: {pos['target1']} | 目标2: {pos['target2']}")
    else:
        print("\n【持仓明细】暂无持仓")
    
    # 主要指数收盘
    print("\n【主要指数收盘】")
    indices = [
        ('000001', '上证指数'),
        ('399001', '深证成指'),
        ('399006', '创业板指'),
        ('000688', '科创50')
    ]
    
    for symbol, name in indices:
        df = analyzer.get_index_data(symbol)
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            change = latest['close'] - prev['close']
            change_pct = change / prev['close'] * 100 if prev['close'] != 0 else 0
            ma5 = round(df['close'].tail(5).mean(), 3)
            ma20 = round(df['close'].tail(20).mean(), 3) if len(df) >= 20 else ma5
            trend = '↗️上升' if latest['close'] > ma20 else ('↘️下降' if latest['close'] < ma20 else '→震荡')
            print(f"  {name}: {latest['close']:.3f} {'+' if change >= 0 else ''}{change:.3f} ({'+' if change_pct >= 0 else ''}{change_pct:.2f}%) MA5:{ma5} MA20:{ma20} {trend}")
    
    # 今日涨跌停
    print("\n【今日涨跌停】")
    zt_data = analyzer.get_zt_pool()
    print(f"  涨停: {len(zt_data.get('zt', []))} 只")
    print(f"  跌停: {len(zt_data.get('dt', []))} 只")
    
    # 历史交易统计
    if state.get('history'):
        print("\n【历史交易统计】")
        total_profit = sum(h['profit'] for h in state['history'])
        wins = [h for h in state['history'] if h['profit'] > 0]
        losses = [h for h in state['history'] if h['profit'] <= 0]
        print(f"  总交易次数: {len(state['history'])} 次")
        print(f"  盈利次数: {len(wins)} 次")
        print(f"  亏损次数: {len(losses)} 次")
        print(f"  胜率: {len(wins) / len(state['history']) * 100:.1f}%")
        print(f"  总盈亏: {'+' if total_profit >= 0 else ''}{total_profit:.2f} 元")
        if wins and losses:
            avg_win = sum(h['profit'] for h in wins) / len(wins)
            avg_loss = sum(h['profit'] for h in losses) / len(losses)
            print(f"  平均盈利: {avg_win:.2f} 元")
            print(f"  平均亏损: {avg_loss:.2f} 元")
    
    print("\n【明日展望】")
    # 基于当前仓位和市场情况给出建议
    position_ratio = (state['total_value'] - state['cash']) / state['total_value'] if state['total_value'] > 0 else 0
    
    if position_ratio > 0.5:
        print("  当前仓位较重（>50%），明日建议谨慎观察")
        print("  若持仓标的跌破止损位，严格执行止损")
    elif position_ratio > 0.3:
        print("  当前仓位适中（30-50%），可攻可守")
        print("  等待确定性机会再出手")
    else:
        print("  当前仓位较轻（<30%），保存实力")
        print("  等待大盘回调或突破确认后再考虑建仓")
    
    print("\n【投资宪法检查】")
    print("  □ 止损铁律：跌破止损位必须执行")
    print("  □ 仓位上限：单只不超过20%")
    print("  □ 禁止行为：不听消息、不逆势加仓")
    
    print("\n" + "=" * 80)
    
    # 返回结构化数据供定时任务推送
    return {
        'total_value': state['total_value'],
        'total_profit': state['total_profit'],
        'total_profit_pct': state['total_profit_pct'],
        'position_ratio': position_ratio,
        'positions': state['positions'],
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python daily_analysis.py [pre|mid|post]")
        sys.exit(1)
    
    mode = sys.argv[1]
    
    if mode == 'pre':
        pre_market_report()
    elif mode == 'mid':
        mid_market_report()
    elif mode == 'post':
        post_market_report()
    else:
        print(f"未知模式: {mode}")
        sys.exit(1)
