"""临时测试：验证 5 个工具能跑。"""
from app.agent.tools import execute_tool

print("=== 1. list_dir ===")
print(execute_tool("list_dir", {"path": "."}))

print("\n=== 2. read_file ===")
print(execute_tool("read_file", {"path": "preferences.json"}))

print("\n=== 3. search_content ===")
print(execute_tool("search_content", {"keyword": "LLM", "dir": "."}))

print("\n=== 4. write_file ===")
print(execute_tool("write_file", {"path": "test.txt", "content": "hello world"}))

print("\n=== 5. bash (合法命令) ===")
print(execute_tool("bash", {"command": "pwd"}))

print("\n=== 6. bash (非法命令，应被拒绝) ===")
print(execute_tool("bash", {"command": "rm -rf /"}))