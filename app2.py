"""장바구니 역설계 | Python 3.10+
GitHub에 app.py와 requirements.txt 업로드 → Streamlit Community Cloud에서 app.py 배포.
외부 API, 로그인, DB 불필요. 입력은 현재 세션에만 유지됩니다.
재료량·가격은 계산용 예시이며 실제 영양·시세·소비기한 정보가 아닙니다.
QR 공유는 배포 주소를 브라우저에서 QR로 공유하세요. 공용 상태 동기화는 지원하지 않습니다.
"""
import requests
import json
import re
from bs4 import BeautifulSoup
import itertools
import math
import streamlit as st

# 재료: 구매 단위 수량, 단위, 포장 가격. 달걀은 개, 나머지는 g.
ING={
 '쌀':(1000,'g',4500),'달걀':(10,'개',4500),'두부':(300,'g',1800),
 '돼지고기':(500,'g',8000),'닭고기':(500,'g',6500),'양배추':(1000,'g',3500),
 '양파':(1000,'g',2800),'대파':(300,'g',2000),'감자':(1000,'g',4000),
 '당근':(500,'g',2000),'애호박':(300,'g',1800),'김치':(500,'g',5000),
 '참치':(150,'g',2200),'우동면':(400,'g',2400),'어묵':(300,'g',2400),
}
PRICE_INFO = [('쌀', 20000, 65200, '믿고먹는우리쌀 20kg', 'disp/theme/category.ssg?dispCtgId=6000223978'), ('달걀', 10, 5380, '동물복지 유정란 L 10구', 'disp/category.ssg?dispCtgId=6000228040'), ('두부', 300, 1680, '행복한콩 부침두부 300g', 'search.ssg?query=들깨순두부'), ('돼지고기', 500, 9900, '도드람 냉장 미박 앞다리 구이용 500g', 'search.ssg?query=미박앞다리살'), ('닭고기', 500, 11880, '하림 냉장 닭다리살 정육 500g · 정상가', 'disp/category.ssg?dispCtgId=6000215203'), ('양배추', 800, 3480, '한끼 양배추 800g · 정상가', 'search.ssg?query=야채'), ('양파', 4000, 8040, '양파 4kg · 정상가', 'search.ssg?query=야채'), ('대파', 500, 3280, '깐대파 500g · 정상가', 'disp/category.ssg?dispCtgId=6000213178'), ('감자', 2000, 5980, '햇감자 2kg 박스', 'disp/theme/category.ssg?dispCtgId=6000224045'), ('당근', 1000, 5200, '자연맛남 국내산 흙당근 1kg', 'item/itemView.ssg?itemId=1000784715520'), ('애호박', 200, 2980, '인큐 애호박 200g 1입 · 정상가', 'search.ssg?query=야채'), ('김치', 500, 7580, '비비고 썰은배추김치 500g', 'disp/category.ssg?dispCtgId=6000213300'), ('참치', 1500, 23700, '동원 라이트스탠다드 150g 10캔 묶음', 'item/itemView.ssg?itemId=1000708179227'), ('우동면', 2000, 9000, '한일 본고장면 200g 10개 묶음', 'search.ssg?query=우동면사리'), ('어묵', 300, 2980, '대림선 A5종이어묵 300g', 'disp/category.ssg?dispCtgId=6000213254')]
for k,qty,price,name,url in PRICE_INFO:
    ING[k]=(qty,ING[k][1],price)
# 1인분 재료 사용량. 주식이 포함된 계산용 메뉴이며 실제 사용량은 취향에 따라 달라집니다.
REC={
 '김치볶음밥':{'쌀':90,'김치':100,'달걀':1,'대파':15},
 '달걀볶음밥':{'쌀':90,'달걀':2,'당근':30,'대파':15,'양파':40},
 '참치덮밥':{'쌀':90,'참치':75,'달걀':1,'양파':50},
 '두부김치 덮밥':{'쌀':90,'두부':150,'김치':100,'양파':40},
 '돼지고기 양배추덮밥':{'쌀':90,'돼지고기':120,'양배추':120,'양파':50},
 '닭고기덮밥':{'쌀':90,'닭고기':130,'달걀':1,'양파':60},
 '감자달걀 한상':{'쌀':90,'감자':150,'달걀':2,'대파':15},
 '두부채소 한상':{'쌀':90,'두부':150,'애호박':80,'당근':30,'양파':40},
 '닭고기 채소볶음밥':{'쌀':90,'닭고기':100,'양배추':80,'당근':30,'양파':40},
 '돼지고기 김치 한상':{'쌀':90,'돼지고기':120,'김치':120,'두부':80},
 '어묵볶음우동':{'우동면':200,'어묵':80,'양배추':120,'양파':50,'당근':20},
 '닭고기 볶음우동':{'우동면':200,'닭고기':100,'양배추':100,'양파':40},
 '참치김치 덮밥':{'쌀':90,'참치':75,'김치':100,'양파':40},
 '두부달걀 덮밥':{'쌀':90,'두부':100,'달걀':2,'양파':50},
}

def evaluate(menus,people,stock,prices,packs):
    need={k:0 for k in ING}
    for menu in menus:
        for k,v in REC[menu].items():need[k]+=v*people
    rows=[];total=0;surplus_value=0
    for k,n in need.items():
        if n==0:continue
        size=packs[k];price=prices[k];available=stock[k]
        missing=max(0,n-available)
        count=math.ceil(missing/size) if missing else 0
        extra=count*size-missing
        cost=count*price
        total+=cost
        surplus_value+=extra/size*price
        rows.append({'재료':k,'단위':ING[k][1],'필요량':n,'보유량':available,
                     '구매 포장':count,'구매량':count*size,'구매 후 잉여':extra,'금액':cost})
    return {'menus':menus,'rows':rows,'total':total,'surplus':surplus_value}

def optimize(candidates,meals,people,stock,prices,packs,budget,mode):
    if math.comb(len(candidates),meals)>100000:
        raise ValueError('추천 후보가 너무 많습니다. 메뉴 후보를 줄여 주세요.')
    results=[evaluate(c,people,stock,prices,packs) for c in itertools.combinations(candidates,meals)]
    # 예산 안 조합을 우선. 없으면 초과 금액이 가장 적은 조합부터.
    def key(r):
        excess=max(0,r['total']-budget)
        rest=(r['surplus'],r['total']) if mode=='남는 재료 줄이기' else (r['total'],r['surplus'])
        return (excess>0,excess,*rest)
    return sorted(results,key=key)[:3]

def recipe_search(query):
    response=requests.get('https://www.10000recipe.com/recipe/list.html',params={'q':query},timeout=20)
    response.raise_for_status()
    soup=BeautifulSoup(response.text,'html.parser')
    found=[]
    for card in soup.select('.common_sp_list_li'):
        link=card.select_one('a.common_sp_link')
        title=card.select_one('.common_sp_caption_tit')
        if link and title and re.fullmatch(r'/recipe/\d+',link.get('href','')):
            found.append({'title':title.get_text(' ',strip=True),'url':'https://www.10000recipe.com'+link['href']})
    return found[:8]

def recipe_lookup(url):
    if not re.fullmatch(r'https://www\.10000recipe\.com/recipe/\d+',url):
        raise ValueError('지원하지 않는 주소입니다.')
    response=requests.get(url,timeout=20);response.raise_for_status()
    soup=BeautifulSoup(response.text,'html.parser')
    for node in soup.select('script[type="application/ld+json"]'):
        try: obj=json.loads(node.get_text())
        except (ValueError,TypeError):continue
        items=obj if isinstance(obj,list) else [obj]
        for item in items:
            if isinstance(item,dict) and item.get('recipeIngredient'):
                return item
    raise ValueError('원문에서 재료 정보를 찾지 못했습니다.')

def convert_ingredient(line):
    # 원문에 명시된 중량/개수만 변환. 재료명 속 숫자는 사용하지 않습니다.
    text=str(line).replace(',', '')
    aliases={'돼지고기':['돼지고기','목살','삼겹살','앞다리살'],'닭고기':['닭고기','닭다리살','닭가슴살'],
             '쌀':['생쌀'],'참치':['참치'],'김치':['김치'],'달걀':['달걀','계란']}
    key=next((k for k in ING if any(x in text for x in aliases.get(k,[k]))),None)
    if not key:return None,0,'가격 미등록'
    match=re.search(r'(\d+(?:\.\d+)?|\d+/\d+)\s*(kg|킬로그램|g|그램|개|모|캔|봉|줌|큰술|작은술|T|t|컵|ml|mL)',text)
    if not match:return key,0,'분량 불명확'
    raw,unit=match.groups()
    if '/' in raw:
        n,d=raw.split('/');value=float(n)/float(d) if float(d) else 0
    else:value=float(raw)
    if unit in ['kg','킬로그램']:return key,value*1000,'원문 중량'
    if unit in ['g','그램']:return key,value,'원문 중량'
    if unit=='개' and key=='달걀':return key,value,'원문 개수'
    # 대략값은 사용자 입력 대신 앱이 적용하되 근거와 불확실성 공개.
    grams={'양파':200,'대파':100,'당근':150,'감자':180,'애호박':200,'양배추':1000,'달걀':1}
    factors={'모':300 if key=='두부' else None,'캔':150 if key=='참치' else None,
             '봉':ING[key][0],'줌':50,'큰술':15,'작은술':5,'T':15,'t':5,'컵':200}
    factor=grams.get(key) if unit=='개' else factors.get(unit)
    if factor:return key,value*factor,'가정 환산 · 실제 크기 차이 있음'
    return key,0,'환산 불가'


def main():
    st.set_page_config(page_title='우리 집 장바구니',page_icon='🛒',layout='centered')
    st.markdown('<style>.block-container{max-width:540px;padding-top:1.5rem}h1{text-align:center;font-size:1.8rem!important}button{min-height:45px}div[data-testid="stMetricValue"]{font-size:1.6rem}</style>',unsafe_allow_html=True)
    st.title('🛒 우리 집 장바구니')
    st.caption('메뉴 검색 → 담기 → 가족 인원에 맞춰 한 번에 계산')
    people=st.number_input('몇 명이 먹나요?',1,10,3)
    with st.form('search'):
        q=st.text_input('먹고 싶은 메뉴',placeholder='예: 김치찌개')
        go=st.form_submit_button('검색',use_container_width=True)
    if go and q.strip():
        try:
            with st.spinner('검색 중…'):st.session_state['hits']=recipe_search(q.strip())
            if not st.session_state['hits']:st.info('다른 이름으로 검색해 주세요.')
        except requests.RequestException:st.error('검색 사이트 연결이 어렵습니다. 잠시 후 다시 시도해 주세요.')
    hits=st.session_state.get('hits',[])
    if hits:
        pick=st.selectbox('요리 선택',range(len(hits)),format_func=lambda i:hits[i]['title'])
        if st.button('＋ 이 요리 담기',type='primary',use_container_width=True):
            try:
                with st.spinner('재료를 가져오는 중…'):
                    recipe=recipe_lookup(hits[pick]['url'])
                st.session_state.setdefault('cart',[]).append({'recipe':recipe,'url':hits[pick]['url']})
            except (requests.RequestException,ValueError):st.error('재료를 읽지 못했습니다. 다른 레시피를 선택해 주세요.')
    cart=st.session_state.get('cart',[])
    if not cart:
        st.info('먹고 싶은 요리를 검색해서 담으면 아래에 장보기 결과가 바로 나옵니다.')
        return
    st.markdown('### 담은 요리')
    for i,item in enumerate(cart):
        a,b=st.columns([5,1]);a.write(item['recipe'].get('name','요리'))
        if b.button('삭제',key=f'del_{i}'):
            cart.pop(i);st.rerun()
    need={k:0.0 for k in ING};notes=[];missing=[];sources=[]
    for item in cart:
        r=item['recipe'];yield_str=str(r.get('recipeYield',''))
        n=re.search(r'\d+(?:\.\d+)?',yield_str)
        servings=float(n.group()) if n and float(n.group())>0 else None
        if servings is None:
            missing.append(r.get('name','요리')+' · 기준 인원 미상으로 계산 제외')
            continue
        for line in r.get('recipeIngredient',[]):
            key,qty,reason=convert_ingredient(line)
            if key and qty>0:
                need[key]+=qty*people/servings
                notes.append(str(line)+' → '+reason)
            else:missing.append(str(line)+' · '+reason)
        sources.append((r.get('name','원문'),item['url']))
    with st.expander('집에 있는 재료 빼기 · 가격 바꾸기'):
        base=[{'재료':k,'단위':v[1],'보유량':0,'포장량':v[0],'가격':v[2]} for k,v in ING.items() if need[k]>0]
        data=st.data_editor(base,hide_index=True,use_container_width=True,disabled=['재료','단위'],
           column_config={c:st.column_config.NumberColumn(min_value=1 if c=='포장량' else 0,required=True) for c in ['보유량','포장량','가격']}) if base else []
    total=0;rows=[]
    for row in data:
        if any(row.get(c) is None for c in ['보유량','포장량','가격']) or row['포장량']<=0:
            st.warning('포장량은 0보다 크게 입력하세요.');return
        shortage=max(0,need[row['재료']]-row['보유량']);count=math.ceil(shortage/row['포장량'])
        cost=count*row['가격'];total+=cost
        rows.append({'재료':row['재료'],'구매':f"{count}포장",'예상금액':round(cost),'새로 사서 남는 양':f"{max(0,count*row['포장량']-shortage):.1f}{row['단위']}"})
    st.metric('계산 가능한 재료의 예상 구매액',f'{total:,.0f}원')
    if missing:st.warning(f'{len(missing)}개 항목은 금액에 포함되지 않았습니다. 전체 장보기 금액이 아닙니다.')
    if any('가정' in n for n in notes):st.caption('개·모·줌 등은 앱의 대략 환산값을 적용했습니다. 정확한 무게는 원문 또는 제품에서 확인하세요.')
    st.markdown('### 장보기 · 남는 양')
    for row in rows:
        st.checkbox(f"{row['재료']} · {row['구매']} · {row['예상금액']:,}원",key='check_'+row['재료'])
        st.caption('새로 구매해서 남는 양: '+row['새로 사서 남는 양'])
    text='\n'.join(str(x) for x in rows)+'\n추가 확인 필요: '+' / '.join(missing)
    st.download_button('장보기 목록 저장',text.encode('utf-8-sig'),'장보기.txt',use_container_width=True)
    if missing:
        with st.expander('추가로 준비할 재료 · 계산 제외 항목'):
            for x in missing:st.write('• '+x)
    with st.expander('레시피 · 환산 기준 · 가격 출처'):
        for name,url in sources:st.markdown(f'[{name}]({url})')
        for note in notes:st.write(note)
        st.caption('가정: 양파200g/개, 대파100g/개, 당근150g/개, 감자180g/개, 애호박200g/개, 양배추1kg/개, 두부300g/모, 참치150g/캔, 줌50g, 큰술15g, 작은술5g, 컵200g. 재료별 밀도·크기에 따라 차이가 큽니다. 봉은 등록된 구매 포장량을 가정합니다.')
        st.caption('가격은 이전에 수집한 공개 판매 참고값이며 실시간 시장 평균이 아닙니다. 배송비 제외. 메뉴·보유량은 접속 세션에서만 유지되고 가족 휴대폰 간 동기화되지 않습니다.')
        for k,qty,price,name,url in PRICE_INFO:st.markdown(f'{k} · {qty}{ING[k][1]} · {price:,}원 · [판매정보](https://emart.ssg.com/{url})')


def legacy_calculator():
    # 사용자가 추가한 메뉴는 현재 세션에서만 유지합니다.
    for k,v in st.session_state.get('my_ingredients',{}).items():
        ING[k]=v
    REC.update(st.session_state.get('my_recipes',{}))
    st.info('① 메뉴 직접 쓰기 → ② 재료·인원 확인 → ③ 장보기 계산')
    with st.expander('＋ 원하는 메뉴가 없나요? 직접 추가하기'):
        st.caption('메뉴 이름과 1인분 재료량을 등록하면 같은 방식으로 구매 금액을 계산합니다. 메뉴·재료는 이 접속 세션에서만 유지됩니다.')
        with st.form('new_ingredient'):
            st.write('목록에 없는 재료 추가 (필요한 경우만)')
            ik=st.text_input('재료 이름',max_chars=30)
            iu=st.selectbox('단위',['g','mL','개'])
            iq=st.number_input('한 포장에 들어 있는 양',1,100000,500)
            ip=st.number_input('한 포장 가격 (원 · 직접 입력)',0,1000000,3000)
            if st.form_submit_button('재료 등록'):
                if not ik.strip():st.error('재료 이름을 입력하세요.')
                elif ik.strip() in ING:st.error('이미 있는 재료입니다. 기존 가격 수정 기능을 이용하세요.')
                else:
                    st.session_state.setdefault('my_ingredients',{})[ik.strip()]=(iq,iu,ip)
                    st.rerun()
        with st.form('new_recipe'):
            title=st.text_input('추가할 메뉴 이름',placeholder='예: 우리 집 닭볶음탕',max_chars=50)
            rows=st.data_editor([{'재료':k,'단위':v[1],'1인분 사용량':0} for k,v in ING.items()],hide_index=True,
                disabled=['재료','단위'],use_container_width=True,
                column_config={'1인분 사용량':st.column_config.NumberColumn(min_value=0,step=1,required=True)})
            if st.form_submit_button('메뉴 저장'):
                try:
                    recipe={r['재료']:int(r['1인분 사용량']) for r in rows if int(r['1인분 사용량'])>0}
                    if not title.strip() or not recipe:raise ValueError()
                    if title.strip() in REC:
                        st.error('같은 이름의 메뉴가 있습니다. 다른 이름으로 저장하세요.')
                    else:
                        st.session_state.setdefault('my_recipes',{})[title.strip()]=recipe
                        st.rerun()
                except (ValueError,TypeError):st.error('메뉴 이름과 한 가지 이상의 재료량을 입력하세요.')
    st.markdown('#### ① 먹고 싶은 메뉴를 써주세요')
    menu_text=st.text_area('메뉴 이름 · 한 줄에 하나씩',placeholder='김치찌개\n소고기미역국\n크림파스타',height=110,key='free_menu_text')
    names=[v.strip() for v in menu_text.splitlines() if v.strip()]
    selection_mode='내가 메뉴 고르기'
    chosen=[]
    st.caption('메뉴 이름은 제한 없이 입력할 수 있어요. 이름만으로 재료를 임의 추측하지 않습니다. 처음 보는 메뉴는 아래에서 재료와 1인분 양을 확인해 주세요.')
    for idx,name in enumerate(names):
        if name in REC:
            chosen.append(name)
        else:
            with st.expander(f'{name} · 재료 입력 필요',expanded=True):
                st.caption('재료가 목록에 없으면 위의 「원하는 메뉴가 없나요? 직접 추가하기」에서 재료를 먼저 추가하세요. g·mL·개 단위를 확인하세요.')
                recipe_rows=st.data_editor([{'재료':k,'단위':v[1],'1인분 사용량':0} for k,v in ING.items()],
                    key='free_recipe_'+str(idx)+'_'+name,hide_index=True,use_container_width=True,disabled=['재료','단위'],
                    column_config={'1인분 사용량':st.column_config.NumberColumn(min_value=0,step=1,required=True)})
                recipe={r['재료']:int(r['1인분 사용량'] or 0) for r in recipe_rows if int(r['1인분 사용량'] or 0)>0}
                if recipe:
                    token=f'{name} [입력 {idx+1}]'
                    REC[token]=recipe
                    chosen.append(token)
                    st.session_state.setdefault('my_recipes',{})[token]=recipe
    all_ready=bool(names) and len(chosen)==len(names)
    st.caption('고른 메뉴에 필요한 재료를 합치고, 포장 단위 구매액과 남는 양을 계산합니다.')
    with st.container():
        a,b=st.columns(2)
        people=a.number_input('① 몇 명이 먹나요?',1,8,3)
        meals=b.number_input('추천받을 끼니 수',1,5,3) if selection_mode=='예산에 맞게 추천받기' else len(chosen)
        budget=st.number_input('장보기 예산은 얼마인가요? (원)',0,500000,40000,step=1000)
        with st.expander('선택 설정 · 우선순위와 제외 재료'):
            mode=st.radio('우선순위',['장보기 비용 줄이기','남는 재료 줄이기'],horizontal=True)
            excluded=st.multiselect('빼고 싶은 재료',list(ING),help='알레르기 안전 판정이 아닙니다. 양념과 교차접촉은 별도로 확인하세요.')
        with st.expander('② 집에 있는 재료 입력 · 가격 수정', expanded=True):
            st.caption('집에 있는 재료를 선택하고 양을 적으세요. 모르면 0으로 두세요. 가격은 공개 판매가격 참고값입니다.')
            available=st.multiselect('집에 무엇이 있나요?',list(ING),placeholder='예: 쌀, 달걀, 양파')
            stock_inputs={}
            for k in available:
                stock_inputs[k]=st.number_input(f'{k} 보유량 ({ING[k][1]})',min_value=0,step=1,key='stock_'+k)
            st.caption('조사한 참고가격으로 먼저 계산해도 됩니다. 정확하게 보려면 아래에서 가격을 바꾸세요.')
            with st.expander('마트 포장 크기·가격 바꾸기'):
                base=[{'재료':k,'단위':v[1],'포장량':v[0],'포장가격':v[2]} for k,v in ING.items()]
                edited=st.data_editor(base,hide_index=True,use_container_width=True,disabled=['재료','단위'],
                    column_config={c:st.column_config.NumberColumn(c,min_value=(1 if c=='포장량' else 0),step=1,required=True) for c in ['포장량','포장가격']})
        candidates=list(REC)
        submitted=st.button('③ 예상 금액 · 남는 재료 보기',type='primary',use_container_width=True)
    if submitted and not all_ready:
        st.warning('먹고 싶은 메뉴를 입력하고, 처음 입력한 메뉴는 재료량을 채워주세요.');return
    if submitted:
        stock={};prices={};packs={}
        try:
            for row in edited:
                k=row['재료'];stock[k]=int(stock_inputs.get(k,0));prices[k]=int(row['포장가격']);packs[k]=int(row['포장량'])
                if stock[k]<0 or prices[k]<0 or packs[k]<=0:raise ValueError()
        except (TypeError,ValueError):
            st.error('보유량·가격은 0 이상, 포장량은 1 이상인 정수로 입력하세요.');return
        allowed=[m for m in candidates if not set(REC[m]).intersection(excluded)]
        if selection_mode=='내가 메뉴 고르기' and any(set(REC[m]).intersection(excluded) for m in chosen):
            st.warning('직접 고른 메뉴에 제외 재료가 포함돼 있어요. 메뉴나 제외 조건을 변경해 주세요.');return
        if selection_mode=='예산에 맞게 추천받기' and len(allowed)<meals:
            st.warning('조건에 맞는 서로 다른 메뉴가 부족해요. 제외 재료를 줄이거나 끼니 수를 낮춰주세요.');return
        if selection_mode=='예산에 맞게 추천받기' and math.comb(len(allowed),meals)>100000:
            st.warning('추천 조합이 너무 많습니다. 자동 추천용 메뉴 후보를 줄여주세요.');return
        with st.spinner('메뉴 조합과 포장 수량을 비교하고 있어요…'):
            st.session_state['plans']=([evaluate(chosen,people,stock,prices,packs)] if selection_mode=='내가 메뉴 고르기' else optimize(allowed,meals,people,stock,prices,packs,budget,mode))
            st.session_state['budget']=budget
        st.session_state['choice']=0
    plans=st.session_state.get('plans')
    if plans:
        st.divider()
        st.caption('계산 결과 · 조건을 바꾸면 다시 계산해 주세요.')
        choice=st.selectbox('장바구니 대안',range(len(plans)),key='choice',format_func=lambda i:f"{'추천' if i==0 else '대안 '+str(i)} · {plans[i]['total']:,}원")
        r=plans[choice];a,b=st.columns(2)
        a.metric('예상 장보기 금액',f"{r['total']:,}원")
        diff=st.session_state['budget']-r['total']
        b.metric('예산 잔액' if diff>=0 else '예산 초과',f'{abs(diff):,}원')
        if diff<0:st.warning('현재 식단의 구매액이 예산을 초과합니다. 메뉴·인원·보유량을 조정해 다시 계산하세요.')
        st.markdown('#### 🍽️ 식단')
        for i,menu in enumerate(r['menus'],1):st.write(f'{i}. **{menu}**')
        st.markdown('#### 🛒 장보기')
        buy=[x for x in r['rows'] if x['구매 포장']]
        lines=['장바구니 역설계','식단: '+', '.join(r['menus']),'']
        for row in buy:
            desc=f"{row['재료']} · {row['구매 포장']}포장 ({row['구매량']}{row['단위']}) · {row['금액']:,}원"
            st.checkbox(desc,key=f"buy_{choice}_{desc}")
            lines.append('□ '+desc)
        if not buy:st.success('입력한 보유 재료만으로 준비할 수 있어요.')
        lines.append(f"\n총 구매액: {r['total']:,}원")
        st.download_button('장보기 목록 저장','\n'.join(lines).encode('utf-8-sig'),'장보기목록.txt','text/plain',use_container_width=True)
        st.markdown('#### 🥬 사고 남는 재료')
        leftovers=[x for x in r['rows'] if x['구매 후 잉여']>0]
        if leftovers:
            for row in leftovers:
                st.write(f"• **{row['재료']}** {row['구매 후 잉여']}{row['단위']}")
        else:
            st.success('새로 산 재료는 계산상 남지 않아요.')
        st.caption('위 잔량은 새로 산 재료 중 식단에 쓰고 남는 양입니다. 기존 보유 재료의 잔량은 제외합니다.')
        with st.expander('자세한 계산 보기'):
            st.dataframe(r['rows'],hide_index=True,use_container_width=True)
            st.caption('구매 후 잉여 = 새로 산 양 중 사용하고 남는 양. 기존 보유분의 잔량은 포함하지 않습니다. 잉여 최소화는 g·개를 직접 더하지 않고 포장 가격으로 환산한 금액을 비교합니다.')
        with st.expander('메뉴별 재료 확인'):
            for menu in r['menus']:
                st.write('**'+menu+' · 1인분 기준**')
                st.write(' / '.join(f'{k} {v}{ING[k][1]}' for k,v in REC[menu].items()))
    with st.expander('가격 출처 · 이용 안내'):
        st.warning('전국 시장 평균이나 실시간 가격이 아닙니다. 2026.11.02 검색에서 확인한 공개 판매가격을 수동 반영했습니다. 검색 자료에 과거 행사·배송 일정이 포함돼 현재 판매 여부는 보장하지 않습니다. 결제 전 원문 가격을 확인하세요.')
        for k,qty,price,name,url in PRICE_INFO:
            st.markdown(f"**{k}** · {name} · {price:,}원 · [출처](https://emart.ssg.com/{url})")
        st.caption('표시된 정상가격이 있으면 정상가를 우선 사용했습니다. 그 외는 공개 판매가격으로 할인 여부가 다를 수 있습니다. 배송비·카드혜택·기본양념·에너지비용 제외. 참치·우동은 실제 확인한 묶음 전체를 구매하는 기준이라 잔량이 클 수 있습니다. 가격·포장 크기를 수정할 수 있습니다. 밥은 생쌀 기준. 알레르기·보관 상태는 별도 확인하세요. 입력은 세션에만 유지됩니다.')

if __name__=='__main__':main()
