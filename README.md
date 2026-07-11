# 爱尔兰生活咨询网站（新版）

已按绿色微信支付风格重做，包含：
- 手机端首页
- 单选咨询主题
- 微信扫码支付30元
- 上传付款截图
- 客户实时聊天
- 后台确认付款并开始30分钟倒计时
- 管理员桌面新消息通知

本地运行：
pip install -r requirements.txt
python app.py

客户页面：http://127.0.0.1:5000
后台：http://127.0.0.1:5000/admin
默认后台密码：admin123

正式上线前请通过环境变量修改 ADMIN_PASSWORD 和 SECRET_KEY。
