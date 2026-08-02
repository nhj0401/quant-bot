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
        self.wfile.write("🔥 Quant Bot V42.1 (Hotfix 400 Error) is Alive!".encode('utf-8'))
    def log_message(self, format, *args): return 

def run_web_server():
    HTTPServer(('0.0.0.0', 8080), HealthCheckHandler).serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 🔒 환경 변수: 초고속 Groq 엔진
# ==========================================
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY') 

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

def get_market_status():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    now_str = now.strftime(f"%Y년 %m월 %d일 {weekdays[now.weekday()]} %H:%M")
    
    is_summer = 3 <= now.month <= 11
    open_h, open_m = (22, 30) if is_summer else (23, 30)
    close_h = 5 if is_summer else 6
    
    curr_mins = now.hour * 60 + now.minute
    open_mins = open_h * 60 + open_m
    close_mins = close_h * 60
    wd = now.weekday()
    
    is_closed = False
    if wd == 5 and curr_mins >= close_mins: is_closed = True
    elif wd == 6: is_closed = True
    elif wd == 0 and curr_mins < open_mins: is_closed = True
        
    if is_closed: return now_str, f"💤 **현재 미국 증시는 [주말 휴장]입니다.** (다음 개장: 월요일 {open_h}:{open_m})"
    if curr_mins < close_mins: return now_str, f"🔥 **미국 증시 [정규장 진행 중]** (마감: 오늘 {close_h:02d}:00)"
    elif curr_mins >= open_mins: return now_str, f"🔥 **미국 증시 [정규장 진행 중]** (마감: 내일 {close_h:02d}:00)"
    else: return now_str, f"⏳ **현재 [프리마켓 / 대기장]** (개장: 오늘 {open_h}:{open_m})"

@bot.event
async def on_ready():
    print(f"🔥 V42.1 핫픽스(통신 400 에러 해결) 가동 완료!")
    if not memory_cleanup_task.is_running(): memory_cleanup_task.start()
    if not autonomous_recon.is_running(): autonomous_recon.start()

@tasks.loop(minutes=15.0)
async def memory_cleanup_task():
    curr = time.time()
    for k in [k for k, v in data_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del data_cache[k]
    for k in [k for k, v in ai_response_cache.items() if (curr - v['timestamp']) > CACHE_TTL]: del ai_response_cache[k]

def get_loading_embed():
    _, market_msg = get_market_status()
    return discord.Embed(
        title="⚡ 초고속 퀀트 AI 분석 중...", 
        description=f"Llama-3 최신 엔진이 데이터를 스캔 중입니다.\n\n🕒 {market_msg}", 
        color=0x3498DB
    )

def get_nuke_loading_embed():
    _, market_msg = get_market_status()
    return discord.Embed(
        title="☢️ [오메가 프로토콜] 가동 중...", 
        description=f"모든 지표와 심리를 응축하여 최종 작전 명령서를 작성하고 있습니다.\n\n🕒 {market_msg}", 
        color=0xE74C3C
    )

# ------------------------------------------
# ⚡ 초고속 Groq API 코어 (토스 맞춤형 + 디버거)
# ------------------------------------------
async def ask_ai_async(prompt, system_role):
    if not GROQ_API_KEY: return "🚨 GROQ API 키가 Render에 등록되지 않았습니다."
    cache_key = f"{system_role}_{prompt}"
    curr = time.time()
    if cache_key in ai_response_cache and (curr - ai_response_cache[cache_key]['timestamp']) < CACHE_TTL:
        return ai_response_cache[cache_key]['text']

    master_system_role = f"""너는 고등학교 1학년 트레이더를 위한 'AI 퀀트 참모'야. 
자본금 1~5만 원 단위의 소수점 투자 및 '토스(Toss) 증권 앱'을 이용한 단타(CQB)에 능해. 
토스 앱은 호가창이 얇고 딜레이가 있으므로, 확실한 자리에서만 진입하도록 지시해.
트레이더님은 특수부대와 경찰을 꿈꾸며 체력을 단련하고 있어.
[역할 지정]: {system_role}
[출력 원칙]: 반드시 한국어로 답변. 이유와 원리를 고등학생 눈높이에서 아주 상세하게 설명할 것. 마크다운 표 적극 활용. 특수작전과 헬스/유도에 빗대어 엄격하게 조언해라."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    
    # 🌟 V42.1 수정: Groq의 가장 최신, 안정적인 칩셋으로 교체
    payload = {
        "model": "llama-3.3-70b-versatile", 
        "messages": [
            {"role": "system", "content": master_system_role},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    
    async with api_semaphore:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=payload, timeout=15.0) as res:
                    if res.status == 200:
                        data = await res.json()
                        ans_text = data['choices'][0]['message']['content']
                        ai_response_cache[cache_key] = {'text': ans_text, 'timestamp': time.time()}
                        return ans_text
                    else:
                        # 🌟 에러 상세 텍스트 추출 (무엇 때문에 400 에러가 났는지 그대로 반환)
                        error_text = await res.text()
                        return f"🚨 **통신 오류 ({res.status})**\nGroq 서버 응답: `{error_text[:250]}...`\n(이 메시지가 계속 뜨면 칩셋 이름이 또 바뀌었거나 입력값에 문제가 있는 것입니다.)"
            except Exception as e:
                return f"🚨 네트워크 통신 실패: {e}"

# ------------------------------------------
# 🖥️ 기본 UI 모달들
# ------------------------------------------
class TickerSearchModal(discord.ui.Modal, title='🔍 종목 검색'):
    company_name = discord.ui.TextInput(label='회사명', placeholder='예: 애플')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"'{self.company_name.value}'의 미국 주식 코드를 찾고, 비즈니스 모델을 상세히 설명해.", "검색 봇")
        await interaction.edit_original_response(embed=discord.Embed(title="🔍 검색 결과", description=ans, color=0x2ECC71))

class DCAModal(discord.ui.Modal, title='⚖️ 매수 타점'):
    ticker = discord.ui.TextInput(label='주식 코드')
    budget = discord.ui.TextInput(label='예산 (원)')
    async def on_submit(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중.", ephemeral=True)
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}, 예산: {self.budget.value}원. 토스 소수점 투자를 활용해 매수 전술을 짜줘.", "전술 파트너")
        await interaction.edit_original_response(embed=discord.Embed(title=f"⚖️ {self.ticker.value.upper()} 매매 지시서", description=ans, color=0x2ECC71))

class PanicRoomModal(discord.ui.Modal, title='🧘 패닉 룸'):
    ticker = discord.ui.TextInput(label='불안한 종목')
    reason = discord.ui.TextInput(label='이유', style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        ans = await ask_ai_async(f"종목: {self.ticker.value.upper()}, 이유: '{self.reason.value}'. 멘탈을 꽉 잡아주는 팩트폭격을 해라.", "훈련 교관")
        await interaction.edit_original_response(embed=discord.Embed(title="🧘 멘탈 방어선", description=ans, color=0x9B59B6))

class GoalSettingModal(discord.ui.Modal, title='🎯 목표 설정'):
    item = discord.ui.TextInput(label='목표 물건')
    price = discord.ui.TextInput(label='목표 금액 (원)')
    async def on_submit(self, interaction: discord.Interaction):
        user_goals[interaction.user.id] = {'item': self.item.value, 'price': float(self.price.value.replace(',', ''))}
        await interaction.response.send_message("🎯 **목표 설정 완료!**", ephemeral=True)

class OmegaProtocolModal(discord.ui.Modal, title='☢️ 전술핵: 오메가 프로토콜'):
    ticker = discord.ui.TextInput(label='분석할 종목 코드')
    budget = discord.ui.TextInput(label='총예산 (원)')
    async def on_submit(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차트 접근 차단 중.", ephemeral=True)
        await interaction.response.send_message(embed=get_nuke_loading_embed())
        prompt = f"""종목: {self.ticker.value.upper()}, 예산: {self.budget.value}원. 토스(Toss) 앱 사용 중.
재무/차트/수급/심리를 융합해 '오메가 프로토콜'을 작성해라. 토스 환경에 맞게 며칠간 얼마씩 살지, 칼손절은 어디인지 수치로 하달해라."""
        ans = await ask_ai_async(prompt, "최고 사령관")
        await interaction.edit_original_response(embed=discord.Embed(title=f"☢️ [오메가 프로토콜] {self.ticker.value.upper()}", description=ans, color=0xE74C3C))

# ------------------------------------------
# 💡 툴 입력창용 모달 (융합 분석 지원)
# ------------------------------------------
class QuantToolModal(discord.ui.Modal):
    def __init__(self, tool_name: str, category: str):
        title = "🛠️ 다중 융합 전술 분석" if "," in tool_name else f"🛠️ {tool_name[:30]}"
        super().__init__(title=title)
        self.tool_name = tool_name
        self.category = category
        self.input_val = discord.ui.TextInput(label='분석 대상 (종목 등)')
        self.add_item(self.input_val)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_loading_embed())
        if self.category == "daytrade":
            prompt = f"가동 전술들: '{self.tool_name}', 대상 종목: '{self.input_val.value.upper()}'. 토스(Toss) 앱으로 단타를 친다. 선택된 여러 전술들을 완벽하게 융합하여 호가창 리스크와 단기 흐름을 구체적으로 분석하고 칼손절 원칙을 강조해라."
        else:
            prompt = f"가동 전술들: '{self.tool_name}', 대상 종목: '{self.input_val.value.upper()}'. 고등학교 1학년 눈높이에 맞춰 선택된 툴들의 의미를 종합하고 현재 종목에 어떻게 융합 적용되는지 아주 상세하게 브리핑해라."
            
        ans = await ask_ai_async(prompt, "퀀트 맥가이버")
        await interaction.edit_original_response(embed=discord.Embed(title=f"🔥 결과: {self.input_val.value.upper()} 융합 리포트", description=ans, color=0x95A5A6))

# ------------------------------------------
# 🗂️ 드롭다운 3종 (최대 5개 동시 체크 가능)
# ------------------------------------------
class GeneralSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. 🩺 재무 엑스레이 스캔"), discord.SelectOption(label="2. ⚖️ 손익비(RR) 계산기"),
            discord.SelectOption(label="3. ❄️ 배당금 복리 머신"), discord.SelectOption(label="4. 📊 섹터 테마 스캐너"),
            discord.SelectOption(label="5. 📰 호재/악재 팩트체크"), discord.SelectOption(label="6. 🏢 라이벌 비교 스캔"),
            discord.SelectOption(label="7. 📅 어닝(실적) 충격 분석"), discord.SelectOption(label="8. 📉 구조대(물타기) 계산기"),
            discord.SelectOption(label="9. 📈 ETF 방패막이 확인"), discord.SelectOption(label="10. 💰 10대 소액 맞춤 플래너")
        ]
        super().__init__(placeholder="🟢 [일반 훈련] (최대 5개 동시 체크 가능)", min_values=1, max_values=5, options=options)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중", ephemeral=True)
        selected = ", ".join(self.values)
        await interaction.response.send_modal(QuantToolModal(tool_name=selected, category="general"))

class SpecialSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. 📡 세력(고래) 수급 레이더"), discord.SelectOption(label="2. 🎯 스나이퍼 타점 (RSI)"),
            discord.SelectOption(label="3. 💸 타임머신 백테스트"), discord.SelectOption(label="4. 💥 숏커버링 폭발 예측"),
            discord.SelectOption(label="5. 💣 상폐 지뢰밭 탐지기"), discord.SelectOption(label="6. 🚀 내부자 매수 포착"),
            discord.SelectOption(label="7. 🦇 다크풀 그림자 추적"), discord.SelectOption(label="8. 🔥 광기 버블 경보"),
            discord.SelectOption(label="9. 🐺 야수의 심장 모드"), discord.SelectOption(label="10. 🕵️ VIX 폭락장 방어")
        ]
        super().__init__(placeholder="🔴 [특수 작전] (최대 5개 동시 체크 가능)", min_values=1, max_values=5, options=options)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중", ephemeral=True)
        selected = ", ".join(self.values)
        await interaction.response.send_modal(QuantToolModal(tool_name=selected, category="special"))

class DayTradeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. ⚡ 1분봉 스캘핑 타점 판독기"), discord.SelectOption(label="2. 🚀 시초가 갭상승 스나이퍼"),
            discord.SelectOption(label="3. 💣 거래량 폭발 돌파 매매"), discord.SelectOption(label="4. 🩸 급락 눌림목 암살 전술"),
            discord.SelectOption(label="5. 🛡️ -2% 칼손절 강제 탈출"), discord.SelectOption(label="6. 🧊 VI 예측"),
            discord.SelectOption(label="7. 📉 투매 폭포수 경보"), discord.SelectOption(label="8. 🧠 뇌동매매(FOMO) 차단기"),
            discord.SelectOption(label="9. 💸 반익절 가이드"), discord.SelectOption(label="10. 🕵️ 장전 수급 스파이"),
            discord.SelectOption(label="11. ⚖️ 얇은 호가창 지뢰밭 탐지"), discord.SelectOption(label="12. 📊 VWAP 기준선 판독"),
            discord.SelectOption(label="13. 📉 쌍봉 하락 패턴 탐지"), discord.SelectOption(label="14. 🎣 밑꼬리 반등 낚시 전술"),
            discord.SelectOption(label="15. 💊 복수 매매 진정제"), discord.SelectOption(label="16. 🤖 매크로 추적"),
            discord.SelectOption(label="17. 🙏 기도 매매 팩트 폭격기"), discord.SelectOption(label="18. 🏆 거래대금 싹쓸이 스캔"),
            discord.SelectOption(label="19. ⏳ 3분 홀딩 멘탈 테스트"), discord.SelectOption(label="20. 🐺 초변동성 심박수 측정")
        ]
        super().__init__(placeholder="⚡ [CQB 단타 전술] (최대 5개 동시 체크 가능)", min_values=1, max_values=5, options=options)
    async def callback(self, interaction: discord.Interaction):
        if exam_mode.get(interaction.user.id, False): return await interaction.response.send_message("🛡️ 차단 중", ephemeral=True)
        selected = ", ".join(self.values)
        await interaction.response.send_modal(QuantToolModal(tool_name=selected, category="daytrade"))

# ------------------------------------------
# 🎛️ 대시보드 UI 세팅
# ------------------------------------------
class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="🔍 검색", style=discord.ButtonStyle.primary, custom_id="search", row=0))
        self.add_item(discord.ui.Button(label="⚖️ 타점", style=discord.ButtonStyle.success, custom_id="dca", row=0))
        self.add_item(discord.ui.Button(label="🧘 패닉룸", style=discord.ButtonStyle.danger, custom_id="pan", row=0))
        self.add_item(discord.ui.Button(label="🎯 목표", style=discord.ButtonStyle.success, custom_id="goal", row=0))
        self.add_item(GeneralSelect()) 
        self.add_item(SpecialSelect()) 
        self.add_item(DayTradeSelect()) 
        self.add_item(discord.ui.Button(label="☢️ 오메가 프로토콜 (종합 작전서)", style=discord.ButtonStyle.danger, custom_id="omega", row=4))
        self.add_item(discord.ui.Button(label="🛡️ 시험모드", style=discord.ButtonStyle.primary, custom_id="exam", row=4))
        self.add_item(discord.ui.Button(label="📡 상황실", style=discord.ButtonStyle.secondary, custom_id="alert", row=4))

    async def interaction_check(self, i: discord.Interaction) -> bool:
        cid = i.data.get("custom_id")
        if cid == "dca": await i.response.send_modal(DCAModal())
        elif cid == "pan": await i.response.send_modal(PanicRoomModal())
        elif cid == "search": await i.response.send_modal(TickerSearchModal())
        elif cid == "goal": await i.response.send_modal(GoalSettingModal())
        elif cid == "omega": await i.response.send_modal(OmegaProtocolModal()) 
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

@bot.command(name="시작")
async def start_cmd(ctx):
    now_str, market_msg = get_market_status()
    embed = discord.Embed(
        title="PRO 퀀트 터미널 (V42.1 400에러 해결)", 
        description=f"📅 **현재 시각:** {now_str}\n{market_msg}\n\n🔥 **[최신 AI 칩셋 장착]**\n구형 칩셋을 버리고 최신 엔진으로 교체 완료.\n❓ **`!도움말`**을 치면 전체 사용법이 나옵니다.", 
        color=0x0050FF
    )
    await ctx.send(embed=embed, view=DashboardView())

@bot.command(name="도움말")
async def help_cmd(ctx):
    help_text = """
**🤖 V42.1 특수부대 퀀트 비서 종합 가이드**

**1️⃣ 팁: 다중 융합 분석 (강력 추천) 🔥**
* **드롭다운 안에서 최대 5개까지 여러 전술을 한꺼번에 체크**하고 밖을 누르세요. AI가 5개 전술을 융합하여 단 하나의 리포트를 뽑아냅니다!

**2️⃣ 🟢 [일반 훈련] / 🔴 [특수 작전] / ⚡ [CQB 단타 전술]**
*   가치투자부터 1분봉 초단타까지 40종의 툴이 탑재되어 있습니다.

**3️⃣ 하단 통제실 버튼**
*   ☢️ **오메가 프로토콜:** 재무/수급/차트/심리를 전부 갈아 넣어 1장의 최종 작전 명령서를 작성합니다.
"""
    embed = discord.Embed(title="📖 V42.1 백과사전 가이드", description=help_text, color=0xF1C40F)
    await ctx.send(embed=embed)

bot.run(DISCORD_TOKEN)
