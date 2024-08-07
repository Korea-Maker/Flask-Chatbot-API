import openai
from dotenv import load_dotenv  # 윈도우 사용 시 주석 처리
import os
import time
import re
import json  # Add import for json
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_pymongo import PyMongo
import datetime

# Load .env
load_dotenv()
API_KEY = os.environ.get('API_KEY')  # .env 파일에 저장된 API_KEY를 가져옴
ASSISTANT_ID = os.environ.get('ASSISTANT_ID')  # .env 파일에 저장된 Assistant ID를 가져옴
mongo_username = os.environ.get('MONGO_USERNAME')
mongo_password = os.environ.get('MONGO_PASSWORD')
mongo_host = os.environ.get('MONGO_HOST')
mongo_port = os.environ.get('MONGO_PORT')
mongo_db = os.environ.get('MONGO_DB')

app = Flask(__name__)
app.config['MONGO_URI'] = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{mongo_port}/{mongo_db}"
mongo = PyMongo(app)
CORS(app)

client = openai.OpenAI(api_key=API_KEY)  # API_KEY를 사용하여 OpenAI 클라이언트를 생성

def poll_run(run, thread):
    try:
        while run.status != "completed":
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            time.sleep(0.5)
    except Exception as e:
        print(f"실행 상태를 폴링하는 동안 오류가 발생했습니다. {e}") # 실행 상태를 폴링하는 동안 오류가 발생했습니다.
        return None
    return run


def create_run(thread_id, assistant_id):
    try:
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
        )
    except Exception as e:
        print(f"실행을 만드는 동안 오류가 발생했습니다. {e}") # 실행을 만드는 동안 오류가 발생했습니다.
        return None
    return run

def mongo_find_ip(ip):
    try:
        last_1_hour = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
        responses = mongo.db.responses.find({"client_ip": ip, "_time": {"$gte": last_1_hour}})
        response_list = []
        for response in responses:
            response_list.append(response)
        return len(response_list)
    except Exception as e:
        print(f"Mongodb에서 IP를 찾는 동안 오류가 발생했습니다. {e}")
        return None


@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data['question']
        thread_id = data.get('thread_id', None)
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        if mongo_find_ip(client_ip) >= 5:
            return jsonify({"response": "시간당 최대 5회 질문이 가능합니다. 잠시후 다시 시도 바랍니다."}), 429

        if not user_message:
            return jsonify({"response": "메시지가 입력되지 않았습니다."}), 400

        if thread_id is not None:
            thread = client.beta.threads.retrieve(thread_id)
        else:
            thread = client.beta.threads.create()

        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message
        )
        run = create_run(thread.id, ASSISTANT_ID)

        if run is None:
            return jsonify({"response": "응답을 생성하는데 실패했습니다. project5587@gmail.com 으로 문의주세요."}), 500

        run = poll_run(run, thread)

        if run is None:
            return jsonify({"response": "응답을 생성했으나, 응답을 가져오는데 실패했습니다. project5587@gmail.com 으로 문의주세요."}), 500

        messages = client.beta.threads.messages.list(
            thread_id=thread.id
        )

        messages_list = list(messages)  # 가장 최근의 assistant 메시지를 찾기 위해 메시지를 리스트로 변환 인덱스 [0]이 항상 최신 메시지

        last_message = None
        for message in messages_list:
            if message.role == "assistant":
                last_message = message
                break

        if last_message:
            try:
                response_data = last_message.content[0].text.value
                response_json = json.loads(response_data)  # OpenAI Assistant의 응답이 JSON 형식임을 가정
                
                response_content = response_json.get("response", "")
                suggested_questions = response_json.get("Suggested question", [])
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(f"JSON parsing error: {e}")
                response_content = last_message.content[0].text.value
                suggested_questions = []

            data = {
                "time": datetime.datetime.now(datetime.UTC),
                "client_ip": client_ip,
                "question": user_message,
                "response": response_content,
                "suggested_questions": suggested_questions
            }
            try:
                mongo.db.responses.insert_one({
                    "_time": data["time"],
                    "client_ip": data['client_ip'],
                    "user_message": data['question'],
                    "assistant_message": data['response'],
                    "suggested_questions": data['suggested_questions']
                })
            except Exception as e:
                print(f"Mongodb에 응답을 저장하는데 실패했습니다. {e}")
                return jsonify({"response": "데이터베이스에 응답을 저장하는데 실패했습니다. project5587@gmail.com 로 문의바랍니다."}), 500
            return jsonify({"response": response_content, "suggested_questions": suggested_questions, "thread_id": thread.id})
        else:
            return jsonify({"response": "Assistant로부터 응답이 없습니다. 잠시후 다시 시도해주세요."}), 500
    except Exception as e:
        print(f"엔드포인트에서 예기치 않은 오류가 발생했습니다. {e}")
        return jsonify({"response": "예기치 않은 오류가 발생했습니다."}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port='5050', debug=True)
