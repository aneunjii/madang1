import pandas as pd
import psycopg2
import streamlit as st

# 페이지 기본 설정 (브라우저 탭 제목, 화면을 넓게 사용)
st.set_page_config(page_title="마당 서점", layout="wide")


# ==================== DB 연결 ====================
def get_connection():
    # 접속 정보는 secrets에서 읽어옴 (비밀번호를 코드에 쓰지 않기 위해)
    cfg = st.secrets["postgres"]
    return psycopg2.connect(host=cfg["host"],
                            port=int(cfg.get("port", 5432)),
                            user=cfg["user"],
                            password=cfg["password"],
                            dbname=cfg["database"],
                            sslmode="require")      # Neon은 암호화(SSL) 접속 필수


@st.cache_data(ttl=600)   # 같은 SQL 결과는 10분 동안 캐시에 저장 → rerun 때마다 DB 재조회 X
def run_query(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)                    # %s 자리에 params가 안전하게 들어감
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]      # 열 이름 가져오기
    finally:
        conn.close()                                    # 오류가 나도 연결은 꼭 닫기
    return pd.DataFrame(rows, columns=cols)


# 고객별 구매 횟수·총 구매액 (주문이 없는 고객도 0으로 나오도록 LEFT JOIN)
CUSTOMER_SUMMARY_SQL = """
    SELECT c.custid, c.name,
           COUNT(o.orderid) AS cnt,
           COALESCE(SUM(o.saleprice), 0) AS total
    FROM customer c LEFT JOIN orders o ON c.custid = o.custid
    GROUP BY c.custid, c.name
    ORDER BY c.custid
"""


# ==================== 사이드바 메뉴 ====================
st.sidebar.title("📚 마당 서점")
menu = st.sidebar.radio("메뉴", ["고객 주문 조회", "도서 검색", "매출 대시보드"])


# ==================== ① 고객 주문 조회 ====================
if menu == "고객 주문 조회":
    st.header("👤 고객 주문 조회")

    customers = run_query("SELECT custid, name FROM customer ORDER BY custid")
    name = st.selectbox("고객을 선택하세요", customers["name"].tolist())

    orders = run_query("""
        SELECT o.orderid, c.name, b.bookname, o.saleprice, o.orderdate
        FROM customer c, orders o, book b
        WHERE c.name = %s AND c.custid = o.custid AND b.bookid = o.bookid
        ORDER BY o.orderdate
    """, (name,))

    count = len(orders)
    total = int(orders["saleprice"].sum()) if count > 0 else 0

    col1, col2 = st.columns(2)
    col1.metric("구매 횟수", f"{count}회")
    col2.metric("총 구매액", f"{total:,}원")

    if count == 0:
        st.info(f"'{name}' 고객의 주문 내역이 없어요.")
    else:
        st.dataframe(orders.rename(columns={"orderid": "주문번호", "name": "고객명",
                                            "bookname": "도서명", "saleprice": "판매가",
                                            "orderdate": "주문일"}),
                     hide_index=True)

    st.subheader("전체 고객 구매 요약")
    summary = run_query(CUSTOMER_SUMMARY_SQL)
    st.dataframe(summary.rename(columns={"custid": "고객번호", "name": "고객명",
                                         "cnt": "구매 횟수", "total": "총 구매액"}),
                 hide_index=True)


# ==================== ② 도서 검색 ====================
elif menu == "도서 검색":
    st.header("🔍 도서 검색")

    keyword = st.text_input("도서명 키워드를 입력하세요 (예: 축구, 야구)").strip()

    # ILIKE: 대소문자 구분 없이 '키워드가 포함된' 도서 찾기 (빈칸이면 전체 도서)
    books = run_query("""
        SELECT bookid, bookname, publisher, price
        FROM book
        WHERE bookname ILIKE %s
        ORDER BY bookid
    """, (f"%{keyword}%",))

    if len(books) == 0:
        st.warning(f"'{keyword}'이(가) 들어간 도서가 없어요.")
    else:
        st.write(f"총 **{len(books)}권** 검색됨")
        st.dataframe(books.rename(columns={"bookid": "도서번호", "bookname": "도서명",
                                           "publisher": "출판사", "price": "정가"}),
                     hide_index=True)


# ==================== ③ 매출 대시보드 ====================
elif menu == "매출 대시보드":
    st.header("📊 매출 대시보드")

    cust = run_query(CUSTOMER_SUMMARY_SQL)

    pub = run_query("""
        SELECT b.publisher, SUM(o.saleprice) AS sales
        FROM orders o JOIN book b ON o.bookid = b.bookid
        GROUP BY b.publisher
        ORDER BY sales DESC
    """)

    daily = run_query("""
        SELECT orderdate, SUM(saleprice) AS sales
        FROM orders
        GROUP BY orderdate
        ORDER BY orderdate
    """)

    # 상단 요약 숫자
    col1, col2, col3 = st.columns(3)
    col1.metric("총 매출", f"{int(cust['total'].sum()):,}원")
    col2.metric("총 주문 수", f"{int(cust['cnt'].sum())}건")
    col3.metric("고객 수", f"{len(cust)}명")

    # 고객별 / 출판사별 막대그래프를 나란히
    left, right = st.columns(2)
    with left:
        st.subheader("고객별 총 구매액")
        st.bar_chart(cust.set_index("name")["total"])
    with right:
        st.subheader("출판사별 매출")
        st.bar_chart(pub.set_index("publisher")["sales"])

    # 날짜별 매출 선그래프
    st.subheader("날짜별 매출")
    daily["orderdate"] = pd.to_datetime(daily["orderdate"])
    st.line_chart(daily.set_index("orderdate")["sales"])
