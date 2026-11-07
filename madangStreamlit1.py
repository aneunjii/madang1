import psycopg2
import psycopg2.extras
import pandas as pd
import streamlit as st

# DB 접속 정보는 secrets에서 읽어옴 (배포할 때 비밀번호를 숨기기 위해)
dbConn = psycopg2.connect(st.secrets["postgres"]["url"])
cursor = dbConn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)   # 원본의 DictCursor 역할

st.title("madang")
name = st.text_input("name")                  # 원본의 textEdit

if st.button("Search"):                       # 원본의 pushButton → search_click
    sql = "select o.orderid, c.name, b.bookname, o.saleprice, o.orderdate from Customer c, Orders o, Book b "
    sql += "where c.name='" + name + "' and c.custid=o.custid and b.bookid=o.bookid;"
    cursor.execute(sql)
    result = cursor.fetchall()
    result = pd.DataFrame(result)
    print(result)
    st.dataframe(result)                      # 원본의 tableWidget

    # ==================== [추가 1] 고객의 구매 횟수 · 총 구매액 ====================
    if len(result) == 0:
        st.info(f"'{name}' 고객의 주문 내역이 없어요.")
    else:
        col1, col2 = st.columns(2)
        col1.metric("구매 횟수", f"{len(result)}회")
        col2.metric("총 구매액", f"{int(result['saleprice'].sum()):,}원")


# ==================== [추가 2] 도서명 키워드 검색 ====================
st.divider()
st.header("도서 검색")
keyword = st.text_input("도서명 키워드 (예: 축구, 야구)", key="keyword")

if st.button("도서 검색", key="book_search"):
    # ILIKE: 대소문자 구분 없이 키워드가 '포함된' 도서를 찾음 (%는 앞뒤 아무 글자나 와도 된다는 뜻)
    sql = "select bookid, bookname, publisher, price from Book where bookname ilike %s order by bookid;"
    cursor.execute(sql, ("%" + keyword.strip() + "%",))
    books = pd.DataFrame(cursor.fetchall())

    if len(books) == 0:
        st.warning(f"'{keyword}'이(가) 들어간 도서가 없어요.")
    else:
        st.write(f"총 {len(books)}권 검색됨")
        st.dataframe(books)


# ==================== [추가 3] 매출 대시보드 ====================
st.divider()
st.header("매출 대시보드")

# 고객별 구매 횟수 · 총 구매액 (주문이 없는 고객도 0으로 나오도록 LEFT JOIN)
cursor.execute("""
    select c.name, count(o.orderid) as cnt, coalesce(sum(o.saleprice), 0) as total
    from Customer c left join Orders o on c.custid = o.custid
    group by c.custid, c.name
    order by c.custid;
""")
cust = pd.DataFrame(cursor.fetchall())

# 출판사별 매출
cursor.execute("""
    select b.publisher, sum(o.saleprice) as sales
    from Orders o join Book b on o.bookid = b.bookid
    group by b.publisher
    order by sales desc;
""")
pub = pd.DataFrame(cursor.fetchall())

# 날짜별 매출
cursor.execute("""
    select orderdate, sum(saleprice) as sales
    from Orders
    group by orderdate
    order by orderdate;
""")
daily = pd.DataFrame(cursor.fetchall())

# 상단 요약 숫자
col1, col2, col3 = st.columns(3)
col1.metric("총 매출", f"{int(cust['total'].sum()):,}원")
col2.metric("총 주문 수", f"{int(cust['cnt'].sum())}건")
col3.metric("고객 수", f"{len(cust)}명")

st.subheader("고객별 구매 횟수 · 총 구매액")
st.dataframe(cust)
st.bar_chart(cust.set_index("name")["total"])

st.subheader("출판사별 매출")
st.bar_chart(pub.set_index("publisher")["sales"])

st.subheader("날짜별 매출")
daily["orderdate"] = pd.to_datetime(daily["orderdate"])
st.line_chart(daily.set_index("orderdate")["sales"])

dbConn.close()                                # 화면을 다 그린 뒤 DB 연결 정리
