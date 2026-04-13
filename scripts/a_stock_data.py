#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股数据获取脚本 - 精算师专用
稳定版：mootdx主源 + akshare备用 + 超时控制
"""

import warnings
warnings.filterwarnings('ignore')

import sys
import time
import signal
import logging
from datetime import datetime
from typing import Optional, Dict, List

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== 超时控制 ==========

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("操作超时")

# ========== 数据源配置 ==========

MOOTDX_SERVERS = [
    ('124.70.199.56', 7709),
    ('124.70.176.52', 7709),
    ('121.36.54.217', 7709),
]

# ========== 数据获取 ==========

def get_mootdx_client(timeout=10):
    """获取 mootdx 客户端"""
    from mootdx.quotes import Quotes
    
    for server in MOOTDX_SERVERS:
        try:
            client = Quotes.factory(market='std', server=server, timeout=timeout)
            df = client.index(symbol='000001', frequency=9, offset=1)
            if df is not None and len(df) > 0:
                logger.info(f"mootdx 连接成功: {server}")
                return client
        except:
            continue
    logger.error("mootdx 所有服务器连接失败")
    return None


def is_trading_time():
    """检查是否为交易时间"""
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:  # 周末
        return False
    hour = now.hour
    minute = now.minute
    # 9:15-11:30, 13:00-15:00
    if hour == 9 and minute >= 15:
        return True
    if hour == 10 or hour == 11:
        return True
    if hour == 13 and minute < 60:
        return True
    if hour == 14 or hour == 15:
        return True
    return False


def get_indices(client):
    """获取主要指数"""
    indices_map = [
        ('000001', '上证指数'),
        ('399001', '深证成指'),
        ('399006', '创业板指'),
        ('000300', '沪深300'),
    ]
    
    results = {}
    for symbol, name in indices_map:
        try:
            df = client.index(symbol=symbol, frequency=9, offset=1)
            if df is not None and len(df) > 0:
                latest = df.iloc[-1]
                # 获取昨日收盘价计算涨跌幅
                if len(df) >= 2:
                    prev_close = df.iloc[-2]['close']
                    close = latest['close']
                    change_pct = (close - prev_close) / prev_close * 100 if prev_close > 0 else 0
                else:
                    change_pct = 0
                
                results[name] = {
                    'price': latest['close'],
                    'change_pct': change_pct,
                    'datetime': latest.get('datetime', ''),
                }
        except Exception as e:
            logger.warning(f"获取 {name} 失败")
    return results


def get_zt_pool(timeout=15):
    """获取涨跌停数据"""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)
    
    try:
        import akshare as ak
        date = datetime.now().strftime("%Y%m%d")
        df = ak.stock_zt_pool_em(date=date)
        signal.alarm(0)
        
        if df is not None and len(df) > 0:
            zt = df[df['涨跌幅'] >= 9.9]
            dt = df[df['涨跌幅'] <= -9.9]
            
            # 获取涨停股详情
            top_zt = []
            if len(zt) > 0:
                top = zt.nlargest(5, '成交额')
                for _, row in top.iterrows():
                    code = row.get('代码', row.name)
                    name = row.get('名称', code)
                    amount = row.get('成交额', 0)
                    top_zt.append(f"{name}({code})")
            
            return {
                'zt_count': len(zt),
                'dt_count': len(dt),
                'top_zt': top_zt,
            }
    except TimeoutError:
        logger.warning("涨跌停数据获取超时")
    except Exception as e:
        logger.warning(f"涨跌停获取失败: {e}")
    finally:
        signal.alarm(0)
    
    return {'zt_count': '超时', 'dt_count': '超时', 'top_zt': []}


def get_hsgt(timeout=15):
    """获取北向资金"""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)
    
    try:
        import akshare as ak
        df = ak.stock_hsgt_fund_flow_summary_em()
        signal.alarm(0)
        
        if df is not None and len(df) > 0:
            north = df[df['资金方向'] == '北向']
            results = {}
            for _, row in north.iterrows():
                net = row.get('净买入额', 0)
                results[row['板块']] = net / 100000000
            return results
    except TimeoutError:
        logger.warning("北向资金获取超时")
    except Exception as e:
        logger.warning(f"北向资金获取失败: {e}")
    finally:
        signal.alarm(0)
    
    return {}


# ========== 主函数 ==========

def get_daily_briefing():
    """获取每日简报"""
    output = []
    output.append("=" * 60)
    output.append("【精算师】A股实时行情速览")
    output.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    output.append("=" * 60)
    
    # 交易状态提示
    is_trading = is_trading_time()
    if not is_trading:
        output.append("\n⏰ 当前非交易时间，显示上一交易日数据")
    
    # 1. 主要指数
    output.append("\n📊 主要指数：")
    client = get_mootdx_client()
    if client:
        indices = get_indices(client)
        for name, data in indices.items():
            change = data['change_pct']
            arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
            output.append(f"  {name}: {data['price']:.2f} ({change:+.2f}%) {arrow}")
        client.close()
    else:
        output.append("  ❌ mootdx 连接失败")
    
    # 2. 涨跌停
    output.append("\n📈 涨跌停：")
    zt = get_zt_pool()
    output.append(f"  涨停: {zt['zt_count']} 只")
    output.append(f"  跌停: {zt['dt_count']} 只")
    if zt['top_zt']:
        output.append("  热门涨停: " + " | ".join(zt['top_zt'][:3]))
    
    # 3. 北向资金
    output.append("\n🌐 北向资金：")
    hsgt = get_hsgt()
    if hsgt:
        for market, net in hsgt.items():
            arrow = "流入 ↑" if net > 0 else "流出 ↓"
            output.append(f"  {market}: {net:.2f}亿 {arrow}")
    else:
        output.append("  获取超时或无数据")
    
    output.append("\n" + "=" * 60)
    output.append("主数据源: mootdx(通达信) | 备用: akshare")
    output.append("=" * 60)
    
    return "\n".join(output)


if __name__ == "__main__":
    print(get_daily_briefing())
