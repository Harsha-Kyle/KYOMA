with open(r'c:\Users\harsh\Downloads\LocalAIVtuber2-master\LocalAIVtuber2-master\backend\server.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('/ws/esp32')
if idx != -1:
    print(content[idx-100:idx+1500])
else:
    print("Endpoint not found!")
