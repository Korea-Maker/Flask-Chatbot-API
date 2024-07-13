import openai
from dotenv import load_dotenv # 윈도우 사용 시 주석 처리
import os
import time
import re
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Linux 환경에서 .env 파일을 사용하기 위해 아래 코드를 추가
# Load .env
load_dotenv()
API_KEY = os.environ.get('API_KEY')  # .env 파일에 저장된 API_KEY를 가져옴
ASSISTANT_ID = os.environ.get('ASSISTANT_ID')  # .env 파일에 저장된 Assistant ID를 가져옴

# # Windows 환경에서 .env 파일을 사용하기 위해 아래 코드를 추가
# API_KEY = os.getenv('API_KEY')  # .env 파일에 저장된 API_KEY를 가져옴
# ASSISTANT_ID = os.getenv('ASSISTANT_ID')  # .env 파일에 저장된 Assistant ID를 가져옴

client = openai.OpenAI(api_key=API_KEY)  # API_KEY를 사용하여 OpenAI 클라이언트를 생성

def poll_run(run, thread):
    while run.status != "completed":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )
        time.sleep(0.5)
    return run

def create_run(thread_id, assistant_id):
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )
    return run

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data['question']
    thread_id = data.get('thread_id', None) # thread_id 값이 없을 경우 None으로 초기화

    if not user_message:
        return jsonify({"error": "Not Message"}), 400

    if thread_id != None:
        thread = client.beta.threads.retrieve(thread_id) # thread_id 값이 있을 경우 해당 thread_id를 사용하여 쓰레드를 가져옴
    else:
        thread = client.beta.threads.create() # thread_id 값이 없을 경우 새로운 쓰레드를 생성

    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message
    )
    run = create_run(thread.id, ASSISTANT_ID)

    poll_run(run, thread)

    messages = client.beta.threads.messages.list(
        thread_id=thread.id
    )

    messages_list = list(messages) # 가장 최근의 assistant 메시지를 찾기 위해 메시지를 리스트로 변환 인덱스 [0]이 항상 최신 메시지

    # 가장 최근의 assistant 메시지만 출력 / 현재는 이전에 사용하던 thread_id 값을 가져와 사용하지 않아 이전 대화 내용을 기억하지 않으나,
    # 이후 사용자가 이전 대화 내용을 기억하고 이어서 진행할 수 있도록 thread_id 값을 저장하여 사용할 수 있음
    last_message = None
    for message in messages_list:
        if message.role == "assistant":
            last_message = message
            break

    if last_message:
        response_content = re.sub(r'【\d+:\d+†source】', '', last_message.content[0].text.value) # Assistant의 답변에서 source를 제거
        return jsonify({"response": response_content, "thread_id": thread.id})
    else:
        return jsonify({"error": "No response from assistant"}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port='5050', debug=True)


# 현재 응답에 thread_id를 함께 반환하여 다음 대화에서 thread_id를 사용하여 이전 대화 내용을 기억하고 이어서 진행할 수 있도록 함
# 그러나 지속적으로 thread_id를 반환하기 때문에 응답 내용이 많아질 수 있음
# 이후 요청 내 thread_id를 포함하여 요청할 경우 응답에 thread_id를 반환하지 않도록 수정할 예정