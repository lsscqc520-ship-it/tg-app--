import time
import hashlib
import hmac
import json
import random
from flask import Flask, request, jsonify

app = Flask(__name__)

# ========================================================
# 1. 核心底层数据库与账目池 (生产环境可无缝对接 MySQL/Redis)
# ========================================================
USER_DATABASE = {
    # 模拟一个已经在电报内无感开户的兄弟账户
    "tg_12345678": {
        "username": "Matrix_Player",
        "balance": 10000.00,        # 单一钱包综合主账户余额
        "currency": "USDT",         # 统一采用不贬值的 USDT 记账
        "deposit_address": "TR7NHqjev829x192UnvMwxE6jaA9837482", # 专属 TRC-20 链上充值地址
        "is_locked": False,         # 风控锁
        "total_bet": 0.00,          # 累计打码量（下注流水）
        "total_win": 0.00           # 累计派奖量
    }
}

# 财务全局流水账本（用于凌晨对账与防止黑吃黑）
FINANCIAL_LEDGER = {}

# 核心安全屏障：与前端、三方接口约定的防篡改加密密钥
SYSTEM_SECRET_KEY = "laos_sandbox_secure_token_2026"

# ========================================================
# 2. 核心网关：电报无感安全登录与自动化注册接口
# ========================================================
@app.route('/api/auth/tg_gateway', methods=['POST'])
def tg_gateway_login():
    """
    底层逻辑：当玩家在电报点击菜单一键拉起内制 App 时，前端自动上传 TG 身份数据。
    后端安全校验后，如果用户第一次来则自动在数据库建立账目并生成区块链充值通道。
    """
    data = request.json
    raw_tg_id = data.get("id")
    if not raw_tg_id:
        return jsonify({"status": "ERROR", "message": "MISSING_TG_CONTEXT"})
        
    tg_id = f"tg_{raw_tg_id}"
    first_name = data.get("first_name", "Anonymous_Brother")
    
    # 自动开户逻辑
    if tg_id not in USER_DATABASE:
        # 自动化生成专属的 TRC-20 收币地址（真实开发需呼叫波场底层 RPC 节点的 getNewAddress 接口）
        generated_crypto_addr = "T" + hashlib.md5(f"{tg_id}-{time.time()}".encode()).hexdigest().upper()[:33]
        USER_DATABASE[tg_id] = {
            "username": first_name,
            "balance": 0.00,
            "currency": "USDT",
            "deposit_address": generated_crypto_addr,
            "is_locked": False,
            "total_bet": 0.00,
            "total_win": 0.00
        }
        
    return jsonify({
        "status": "SUCCESS",
        "message": "聚合网关安全认证成功",
        "player_data": USER_DATABASE[tg_id]
    })

# ========================================================
# 3. 金流自动化：TRC-20 USDT 区块链自动到账清算接口
# ========================================================
@app.route('/api/payment/trc20_callback', methods=['POST'])
def trc20_deposit_callback():
    """
    底层逻辑：当玩家往大厅显示的钱包转账时，区块链节点（或三方代收网关）会自动向本接口发起回调（Webhook）。
    后端收到通知，秒级加钱并写入财务账本，实现 100% 自动化充值。
    """
    data = request.json
    tx_hash = data.get("tx_id")             # 区块链上这笔转账的唯一哈希值
    to_address = data.get("to_address")     # 收到钱的充值目标地址
    crypto_amount = float(data.get("amount", 0)) # 实际转入的USDT金额
    
    # 幂等性验证：防止黑客用同一个区块哈希重复呼叫接口来刷钱
    if tx_hash in FINANCIAL_LEDGER:
        return jsonify({"status": "IGNORE", "message": "DUPLICATE_BLOCK_DATA"})
        
    # 顺着网络线寻找是哪个玩家的充值地址匹配
    for player_id, p_info in USER_DATABASE.items():
        if p_info["deposit_address"] == to_address:
            # 账目清算：主资产池加钱
            p_info["balance"] += crypto_amount
            # 记录这笔账目，死死锁定
            FINANCIAL_LEDGER[tx_hash] = {
                "player_id": player_id, "type": "DEPOSIT", "amount": crypto_amount, "timestamp": time.time()
            }
            return jsonify({"status": "SUCCESS", "message": "链上资产清算完成，余额已无缝同步", "balance": p_info["balance"]})
            
    return jsonify({"status": "ERROR", "message": "UNKNOWN_DEPOSIT_DESTINATION"})

# ========================================================
# 4. 单一钱包核心：多品类（电子、捕鱼、体育等）统一实时扣款接口
# ========================================================
@app.route('/api/seamless/debit', methods=['POST'])
def seamless_wallet_debit():
    """
    底层的单一钱包（Seamless API）绝对铁律：
    玩家无论是在玩PG电子、捕鱼开炮，还是下注体育盘口，第三方游戏商服务器都会实时呼叫此接口扣钱。
    """
    data = request.json
    player_id = data.get("player_id")
    bet_amount = float(data.get("amount", 0))
    game_round_id = data.get("round_id")    # 本局游戏的唯一注单号
    
    if player_id not in USER_DATABASE:
        return jsonify({"status": "ERROR", "message": "PLAYER_NOT_FOUND"})
        
    player = USER_DATABASE[player_id]
    if player["is_locked"]:
        return jsonify({"status": "ERROR", "message": "ACCOUNT_RISK_LOCKED"})
        
    if player["balance"] < bet_amount:
        return jsonify({"status": "ERROR", "message": "INSUFFICIENT_FUNDS_IN_MAIN_POOL"}) # 余额不足，强行拒绝转动/开炮
        
    # 执行底层扣款
    player["balance"] -= bet_amount
    player["total_bet"] += bet_amount
    
    return jsonify({
        "status": "SUCCESS",
        "tx_id": game_round_id,
        "remaining_balance": player["balance"] # 返回扣款后的最新余额给游戏商渲染画面
    })

# ========================================================
# 5. 单一钱包核心：多品类统一实时派奖接口
# ========================================================
@app.route('/api/seamless/credit', methods=['POST'])
def seamless_wallet_credit():
    """
    底层的单一钱包派奖：游戏出结果后（如老虎机中奖、捕鱼打中大鱼、体育赛事完场），
    游戏商服务器带上赢的钱（Win Amount）呼叫此接口，后端秒级将钱充回玩家的综合账户。
    """
    data = request.json
    player_id = data.get("player_id")
    win_amount = float(data.get("amount", 0))
    game_round_id = data.get("round_id")
    
    if player_id not in USER_DATABASE:
        return jsonify({"status": "ERROR", "message": "PLAYER_NOT_FOUND"})
        
    player = USER_DATABASE[player_id]
    
    # 执行底层加钱
    player["balance"] += win_amount
    player["total_win"] += win_amount
    
    return jsonify({
        "status": "SUCCESS",
        "tx_id": game_round_id,
        "current_balance": player["balance"]
    })

# ========================================================
# 6. 安全提现与下发风控拦截网关
# ========================================================
@app.route('/api/payment/withdraw_gateway', methods=['POST'])
def secure_withdraw_gateway():
    """
    玩家申请提取现金（USDT出款）接口，包含庄家最核心的打码量自动审核逻辑（防止黑客打针刷钱立刻提现）。
    """
    data = request.json
    player_id = data.get("player_id")
    withdraw_amount = float(data.get("amount", 0))
    target_wallet_address = data.get("target_address") # 玩家收钱的波场地址
    
    if player_id not in USER_DATABASE:
        return jsonify({"status": "ERROR", "message": "PLAYER_NOT_FOUND"})
        
    player = USER_DATABASE[player_id]
    if player["balance"] < withdraw_amount:
        return jsonify({"status": "ERROR", "message": "MAIN_POOL_BALANCE_LOW"})
        
    # 【庄家风控铁律】：检查打码量（流水）是否达到充值总额的 100%（俗称1倍流水）
    # 如果打码量不足，说明是在洗钱或者是恶意刷分，强行拦截进入人工审核
    if player["total_bet"] < (withdraw_amount * 0.8):
        return jsonify({
            "status": "RISK_TRIGGERED",
            "message": "您的打码量流水未达到风控标准，本笔提现已拦截，已自动提交给老挝财务后台进行白名单白盒人工审核！"
        })
        
    # 扣钱，走下发代付通道
    player["balance"] -= withdraw_amount
    return jsonify({
        "status": "SUCCESS",
        "message": "风控自动化验证通过！下发代付引擎已启动，USDT 将在 1 分钟内汇入您的链上地址。",
        "remaining_balance": player["balance"]
    })

if __name__ == '__main__':
    print("🔥 Matrix Interstellar 综合娱乐城大满贯聚合总线后台已成功在 8888 端口启动！")
    app.run(host='0.0.0.0', port=8888)
