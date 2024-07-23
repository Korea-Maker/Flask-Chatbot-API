import openai
from dotenv import load_dotenv  # 윈도우 사용 시 주석 처리
import os
import time
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_pymongo import PyMongo

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
        print(f"Error polling run status: {e}")
        return None
    return run


def create_run(thread_id, assistant_id):
    try:
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
        )
    except Exception as e:
        print(f"Error creating run: {e}")
        return None
    return run


@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data['question']
        thread_id = data.get('thread_id', None)  # thread_id 값이 없을 경우 None으로 초기화
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        if thread_id is not None:
            thread = client.beta.threads.retrieve(thread_id)  # thread_id 값이 있을 경우 해당 thread_id를 사용하여 쓰레드를 가져옴
        else:
            thread = client.beta.threads.create()  # thread_id 값이 없을 경우 새로운 쓰레드를 생성

        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message
        )
        run = create_run(thread.id, ASSISTANT_ID)

        if run is None:
            return jsonify({"error": "Failed to create run"}), 500

        run = poll_run(run, thread)

        if run is None:
            return jsonify({"error": "Error while polling run status"}), 500

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
            response_content = re.sub(r'【\d+:\d+†source】', '', last_message.content[0].text.value)  # Assistant의 답변에서 source를 제거
            data = {
                "client_ip": client_ip,
                "question": user_message,
                "response": response_content
            }
            try:
                mongo.db.responses.insert_one({
                    "client_ip": data['client_ip'],
                    "user_message": data['question'],
                    "assistant_message": data['response'],
                })
            except Exception as e:
                print(f"Error inserting document to MongoDB: {e}")
                return jsonify({"error": "Failed to save response to database"}), 500
            return jsonify({"response": response_content, "thread_id": thread.id})
        else:
            return jsonify({"error": "No response from assistant"}), 500
    except Exception as e:
        print(f"General error in /chat endpoint: {e}")
        return jsonify({"error": "An unexpected error occurred"}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port='5050', debug=True)
