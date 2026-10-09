"""启动脚本。"""

import uvicorn

if __name__ == "__main__":
    print("API 启动中...")
    print("接口地址：http://localhost:3000")
    print("接口文档：http://localhost:3000/docs")
    uvicorn.run("app.main:app", host="0.0.0.0", port=3000, reload=True)