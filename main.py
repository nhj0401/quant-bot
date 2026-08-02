import discord
from discord.ext import commands, tasks
import yfinance as yf
import math
import asyncio
import time
import datetime
import os
import aiohttp
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ==========================================
# 🌐 24시간 생존 웹서버
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("🔥 Quant Bot V28.0 (Rate Limit Bypass) is Alive!".encode('utf-8'))
    def log_message(self, format, *args): return 

def run_web_server():
    HTTPServer(('0.0.0.0', 8080), HealthCheckHandler).serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 🔒 환경 변수 및 봇 설정
# ==========================================
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ------------------------------------------
# 🗄️ 글로벌 데이터 & 서버 캐시
# ------------------------------------------
api_semaphore = asyncio.Semaphore(5)
data_cache, ai_response_cache = {}, {}  
user_savings, user_goals, exam_mode = {}, {}, {}
alert_channel_id = None
CACHE_TTL = 600  

@bot.event
async def on_ready():
    print(f'🔥 V28.0 구글 과부하 강제 돌파 패치 완료: {bot.user.name}')
    if not memory_cleanup_task.is_running(): memory_cleanup_task.start()
    if not autonomous_recon.is_running(): autonomous_recon.start()

@tasks.loop(minutes=15.0)
async def memory_cleanup_task():
    curr = time.time()
    for k in [k for k, v in data_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del data_cache[k]
    for k in [k for k, v in ai_response_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del ai_response_cache[k]

def generate_progress_bar(current, total, length=15):
    if total <= 0: return "[오류: 목표 금액 0원]"
    ratio = min(current / total, 1.0)
    filled = int(ratio * length)
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}] {ratio * 100:.1f}%"

# ------------------------------------------
# ⚡ [무적 회피망] AI 코어 엔진 (429 버그 완벽 수정)
# ------------------------------------------
async def ask_ai_async(prompt, system_role):
    cache_key = f"{system_role}_{prompt}"
    curr = time.time()
    if cache_key in ai_response_cache and (curr - ai_response_cache[cache_key]['timestamp']) < CACHE_TTL:
        return ai_response_cache[cache_key]['text']

    master_system_role = f"""너는 고등학교 1학년 트레이더를 위한 'AI 퀀트 및 멘탈 케어 비서'야. 
자본금 1~5만 원 단위의 소수점 투자(DCA)를 가장 효율적으로 리딩하며, 단타와 멘탈 방어 전술에 모두 능해.
트레이더님은 경찰/특수부대를 꿈꾸며 체력(턱걸이, 푸시업, 유도)을 단련하듯 시드머니를 굴리고 있어.
[역할 지정]: {system_role}
[출력 원칙]: 마크다운 표 적극 활용, 수치화, 핵심만 간결하게 지시."""

    payload = {
        "contents": [{"parts": [{"text": f"{master_system_role}\n\n{prompt}"}]}],
        "generationConfig": {"temperature": 0.7}
    }
    
    # 무료 한도가 가장 넉넉한 1.5-flash를 우선 배치
    fallback_models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]
    
    async with api_semaphore:
        async with aiohttp.ClientSession() as session:
            for model_name in fallback_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                
                # 🌟 과부하(429) 발생 시 최대 3번(약 12초간) 물고 늘어지기!
                for attempt in range(3): 
                    try:
                        async with session.post(url, json=payload, timeout=20.0) as res:
                            if res.status == 200:
                                data = await res.json()
                                ans_text = data['candidates'][0]['content']['parts'][0]['text']
                                ai_response_cache[cache_key] = {'text': ans_text, 'timestamp': time.time()}
                                return ans_text
                            elif res.status == 429: # Too Many Requests
                                # 429가 뜨면 4초를 기다렸다가 재시도합니다. (1분 제한 타이머를 녹이기 위함)
                                await asyncio.sleep(4) 
                                continue 
                            elif res.status == 404: 
                                break # 404면 이 모델은 버리고 즉시 다음 모델로!
                            else:
                                break # 알 수 없는 에러도 다음 모델로
                    except Exception:
                        await asyncio.sleep(2)
                        continue # 타임아웃 나면 2초 쉬고 다시 시도
            
            # 모든 시도를 다 했는데도 429에 걸려있다면, 유저에게 진짜 1분을 쉬라고 알려줍니다.
            return "🚨 **[구글 AI 한도 초과]** 무료 API 제한(1분당 15회)이 초과되었습니다. 딱 1분만 기다리신 후 다시 버튼을 눌러주세요!"

async def fetch_stock_async(ticker, period="5d"):
    curr = time.time()
    if ticker in data_cache and (curr - data_cache[ticker]['timestamp']) < CACHE_TTL: return data_cache[ticker]['data']
    async with api_semaphore:
        try:
            hist = await asyncio.to_thread(yf.Ticker(ticker).history, period=period)
            if not hist.empty: data_cache[ticker] = {'data': hist, 'timestamp': curr}
            return hist
        except: return None

# ------------------------------------------
# 🛰️ 24시간 자율 정찰
# ------------------------------------------
@tasks.loop(minutes=30.0)
async def autonomous_recon():
    if not alert_channel_id: return
    ch = bot.get_channel(alert_channel_id)
    if not ch: return
    watch_list = ["TSLA", "NVDA", "SOXL", "AAPL", "SPY"]
    detected = []
    for t in watch_list:
        try:
            hist = await fetch_stock_async(t, "5d")
            if hist is None or len(hist) < 2: continue
            vol_today, vol_yest = hist['Volume'].iloc[-1], hist['Volume'].iloc[-2]
            if vol_yest > 0 and (vol_today / vol_yest) >= 1.8: 
                prc_change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
                detected.append(f"[{t}] 거래량 폭발 (변동: {prc_change:+.2f}%)")
        except: continue

    if detected:
        prompt = f"포착 내용:\n{chr(10).join(detected)}\n이 현상이 투매인지 환희인지 1~10점으로 평가하고 브리핑해라."
        ans = await ask_ai_async(prompt, "정찰 레이더")
        await ch.send(embed=discord.Embed(title="🚨 [긴급] 수급 이상 징후 포착", description=ans, color=0xE74C3C))

# ------------------------------------------
# 🖥️ 상단 UI: 종목 검색기 및 핵심 모달
# ------------------------------------------
class TickerSearchModal(discord.ui.Modal, title='🔍 종목 코드(티커) 검색기'):
    company_name = discord.ui.TextInput(label='회사 이름 (예: 애플, 팔란티어)', placeholder='이름을 입력하세요')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        name = self.company_name.value
        prompt = f"회사명 '{name}'의 미국 주식 공식 종목 코드(티커, Ticker)를 찾아줘. 그리고 이 회사가 돈을 어떻게 버는지 고등학생 눈높이로 딱 1줄로만 재밌게 요약해 줘."
        ans = await ask_ai_async(prompt, "종목 검색 봇")
        await interaction.followup.send(embed=discord.Embed(title=f"🔍 '{name}' 검색 결과", description=ans, color=0x2ECC71))

class DCAModal(discord.ui.Modal, title='⚖️ 소수점 타점 (DCA & 단타)'):
    ticker = discord.ui.TextInput(label='매수할 주식 코드 (알파벳)', placeholder='예: TSLA')
    budget = discord.ui.TextInput(label='투입할 예산 (원)', placeholder='예: 15000')
    async def on_submit(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ **[시험기간 모드]** 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.defer()
        t, bdg = self.ticker.value.upper(), float(self.budget.value.replace(',', ''))
        prompt = f"종목: {t}, 예산: {bdg:,.0f}원. 시장 상태를 진단하고 오늘 얼마치 매수할지 지시해."
        ans = await ask_ai_async(prompt, "전술 파트너")
        await interaction.followup.send(embed=discord.Embed(title=f"⚖️ {t} 매매 지시서", description=ans, color=0x2ECC71))

class SentimentModal(discord.ui.Modal, title='📰 뉴스 감성 분석 (공포/탐욕)'):
    ticker = discord.ui.TextInput(label='주식 코드', placeholder='예: AAPL')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}. 최근 시장 분위기를 종합해 '군중 심리'를 1~10점으로 평가해.", "감성 분석 AI")
        await interaction.followup.send(embed=discord.Embed(title="📰 심리 스캐너", description=ans, color=0x3498DB))

class PanicRoomModal(discord.ui.Modal, title='🧘 멘탈 방어선 (패닉 룸)'):
    ticker = discord.ui.TextInput(label='나를 불안하게 만드는 종목')
    reason = discord.ui.TextInput(label='불안한 이유', style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}, 유저 패닉: '{self.reason.value}'. 멘탈 통제해.", "멘탈 케어 봇")
        await interaction.followup.send(embed=discord.Embed(title="🧘 멘탈 방어선 가동", description=ans, color=0x9B59B6))

class FinancialFilterButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📊 저평가 우량주 발굴", style=discord.ButtonStyle.secondary, custom_id="ff", row=1)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.defer()
        ans = await ask_ai_async("나스닥 빅테크 중, 저평가 종목 2개를 골라 필터링 보고서를 제출해.", "필터링 AI")
        await interaction.followup.send(embed=discord.Embed(title="📊 저평가 리포트", description=ans, color=0xF1C40F))

class HabitJournalModal(discord.ui.Modal, title='📝 훈련 일지 & 시드 장부'):
    saved = discord.ui.TextInput(label='오늘 확보한 시드 (원)', placeholder='예: 1500')
    trade = discord.ui.TextInput(label='매매 복기', required=False)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        uid = interaction.user.id
        amt = float(self.saved.value.replace(',', '')) if self.saved.value else 0
        user_savings[uid] = user_savings.get(uid, 0) + amt
        goal_text = f"\n\n🎯 **목표 진행률:** {generate_progress_bar(user_savings[uid], user_goals[uid]['price'])} ({user_savings[uid]:,.0f}원)" if uid in user_goals else ""
        ans = await ask_ai_async(f"확보 시드: {amt}원. 복기: '{self.trade.value}'. 멘탈 평가해.", "훈련 교관")
        await interaction.followup.send(embed=discord.Embed(title="🔥 단련 일지", description=ans + goal_text, color=0xFFD700))

class GoalSettingModal(discord.ui.Modal, title='🎯 목표 설정'):
    item = discord.ui.TextInput(label='목표 물건', placeholder='예: 나이키 가방')
    price = discord.ui.TextInput(label='목표 금액 (원)', placeholder='예: 50000')
    async def on_submit(self, interaction: discord.Interaction):
        user_goals[interaction.user.id] = {'item': self.item.value, 'price': float(self.price.value.replace(',', ''))}
        await interaction.response.send_message("🎯 **목표 설정 완료!** 일지에 반영됩니다.", ephemeral=True)

# ------------------------------------------
# 💡 하단 고급 드롭다운
# ------------------------------------------
class QuantToolModal(discord.ui.Modal):
    def __init__(self, tool_name: str):
        super().__init__(title=f'🛠️ {tool_name[:30]}')
        self.tool_name = tool_name
        self.input_val = discord.ui.TextInput(label='분석 대상 (종목/단어 등)')
        self.add_item(self.input_val)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ans = await ask_ai_async(f"선택 툴: '{self.tool_name}', 대상: '{self.input_val.value.upper()}'. 전술적 분석해.", "퀀트 파트너")
        await interaction.followup.send(embed=discord.Embed(title=f"결과: {self.tool_name}", description=ans, color=0x95A5A6))

class AdvancedSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. 🩺 재무 엑스레이 스캔", description="단순 매출이 아닌 진짜 뼈대를 분석"),
            discord.SelectOption(label="2. 📡 세력 급증 레이더", description="돈이 무섭게 몰리는 비정상 수급 탐지"),
            discord.SelectOption(label="3. 💸 타임머신 스노우볼", description="과거부터 샀다면 지금 얼마? (백테스트)"),
            discord.SelectOption(label="4. 💥 숏커버링 폭발 예측", description="세력이 기권하고 폭등할 타점 판독"),
            discord.SelectOption(label="5. 💣 상폐/지뢰밭 필터", description="상장폐지 위험 종목 걸러내기")
        ]
        super().__init__(placeholder="👑 추가 고급 퀀트 툴 모음 (상세 분석)", min_values=1, max_values=1, options=options)
        
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.send_modal(QuantToolModal(tool_name=self.values[0]))

# ------------------------------------------
# 🎛️ 대시보드 세팅
# ------------------------------------------
class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="⚖️ 매수 타점", style=discord.ButtonStyle.success, custom_id="dca", row=0))
        self.add_item(discord.ui.Button(label="📰 감성 분석", style=discord.ButtonStyle.secondary, custom_id="sen", row=0))
        self.add_item(discord.ui.Button(label="🧘 패닉 룸", style=discord.ButtonStyle.danger, custom_id="pan", row=0))
        
        self.add_item(discord.ui.Button(label="🔍 종목 검색기", style=discord.ButtonStyle.primary, custom_id="search", row=1))
        self.add_item(FinancialFilterButton())
        self.add_item(discord.ui.Button(label="📝 단련 일지", style=discord.ButtonStyle.secondary, custom_id="hab", row=1))
        
        self.add_item(discord.ui.Button(label="🎯 목표 설정", style=discord.ButtonStyle.success, custom_id="goal", row=2))
        self.add_item(discord.ui.Button(label="🛡️ 시험기간 모드", style=discord.ButtonStyle.primary, custom_id="exam", row=2))
        self.add_item(discord.ui.Button(label="📡 상황실 등록", style=discord.ButtonStyle.danger, custom_id="alert", row=2))

        self.add_item(AdvancedSelect()) 

    async def interaction_check(self, i: discord.Interaction) -> bool:
        cid = i.data.get("custom_id")
        if cid == "dca": await i.response.send_modal(DCAModal())
        elif cid == "sen": await i.response.send_modal(SentimentModal())
        elif cid == "pan": await i.response.send_modal(PanicRoomModal())
        elif cid == "hab": await i.response.send_modal(HabitJournalModal())
        elif cid == "search": await i.response.send_modal(TickerSearchModal())
        elif cid == "goal": await i.response.send_modal(GoalSettingModal())
        elif cid == "exam":
            uid = i.user.id
            if exam_mode.get(uid, False):
                exam_mode[uid] = False
                await i.response.send_message("🔓 **[모드 해제]** 훈련 복귀.", ephemeral=True)
            else:
                exam_mode[uid] = True
                await i.response.send_message("🛡️ **[시험 모드 가동]** 매매 접근 차단.", ephemeral=True)
        elif cid == "alert":
            global alert_channel_id
            alert_channel_id = i.channel.id
            await i.response.send_message("📡 **[상황실 등록 완료]** 24시간 감시망 가동.")
        return True

# ------------------------------------------
# 📌 명령어 및 도움말
# ------------------------------------------
@bot.command(name="시작")
async def start_cmd(ctx):
    embed = discord.Embed(
        title="PRO 퀀트 터미널 (V28.0 한도 초과 방어형)", 
        description="🔥 **[과부하 돌파 알고리즘 가동 중!]**\n구글 서버 횟수 제한에 걸려도 봇이 끈질기게 재시도합니다.\n\n⚠️ 너무 빠르게 여러 버튼을 누르면 구글이 차단할 수 있으니 10초 간격으로 눌러주세요!", 
        color=0x0050FF
    )
    await ctx.send(embed=embed, view=DashboardView())

bot.run(DISCORD_TOKEN)
