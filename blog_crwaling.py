import requests
from bs4 import BeautifulSoup
import time
import pymongo
from dotenv import load_dotenv
import os

def mongo_connect():
    try:
        load_dotenv()
        mongo_username = os.environ.get('MONGO_USERNAME_BLOGS')
        mongo_password = os.environ.get('MONGO_PASSWORD_BLOGS')
        mongo_host = os.environ.get('MONGO_HOST')
        mongo_port = os.environ.get('MONGO_PORT')
        mongo_db = os.environ.get('MONGO_BLOGS_DB')

        if not all([mongo_username, mongo_password, mongo_host, mongo_port, mongo_db]):
            raise ValueError("환경 변수 중 하나 이상이 설정되지 않았습니다.")
        
        client = pymongo.MongoClient(f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{mongo_port}/{mongo_db}")
        db = client[mongo_db]
        collection = db['blogs']
        
        collection.create_index("link", unique=True)
        return collection
    
    except Exception as e:
        print(f"몽고DB에 연결하는 동안 오류가 발생했습니다. {e}")
        return None

def mongo_insert_one(collection, data):
    try:
        # 데이터 검증
        required_fields = ["num", "image", "title", "description", "link"]
        if not all(field in data for field in required_fields):
            raise ValueError("데이터 형식이 올바르지 않습니다.")
        
        collection.insert_one(
            {
                "num": data["num"],
                "image": data["image"],
                "title": data["title"],
                "description": data["description"],
                "link": data["link"]
            }
        )
        print(f"데이터 삽입이 완료되었습니다. {data['num']}")
    except pymongo.errors.DuplicateKeyError as e:
        print(f"중복된 데이터 삽입 시도 {data['num']}")
        return None
    
def get_total_page(url):
    res = requests.get(url)
    soup = BeautifulSoup(res.content, 'html.parser')
    total_page = soup.select_one('#paging > li:nth-child(7) > a > span').get_text()
    return int(total_page)
    
db = mongo_connect()
if db is None:
    print("몽고DB에 연결하는 동안 오류가 발생했습니다.")
else:
    for page in range(1, get_total_page("https://maker5587.tistory.com/") + 1):
        url = f"https://maker5587.tistory.com/?page={page}"

        res = requests.get(url)
        soup = BeautifulSoup(res.content, 'html.parser')
        data = soup.select('.post')

        for index, i in enumerate(data):
            datas = dict() # 빈 딕셔너리로 초기화

            try:
                datas["num"] = (index + 1) + ((page - 1) * 5)
                datas["image"] = i.select_one('.object-cover').get('data-src') if i.select_one('.object-cover') else "No Image"
                datas["title"] = i.select_one('.title').get_text()
                datas["description"] = i.select_one('.summary').get_text()
                datas["link"] = f"https://maker5587.tistory.com{i.select_one('.title a').get('href')}"
                
                mongo_insert_one(db, datas)
                
            except Exception as e:
                print(f"데이터를 가져오는 중 오류가 발생했습니다 {e}")
            finally:
                time.sleep(0.5)