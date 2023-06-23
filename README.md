## Chato

[Chato网址](chato.cn) 可前往注册一个新的机器人。

## 配置

从 config.template.yml 复制一份保存为 config.yml 。然后按照注释完成配置：

``` yaml
HARDWARE: "LX05"           # 你的小爱音箱设备型号（贴在小爱音箱底部）

MI_USER: "YOUR_ACCOUNT"  # 你的米家账号
MI_PASS: "YOUR_PASSWD"    # 你的米家密码

CHATO_API: "YOUR_CHATO_API"  #  chato机器人上面的api

```

其中 `HARDWARE` 是你的小爱音箱设备型号，可以在小爱音箱底部的标签里找到。

## 使用

``` bash
python chato.py
```


## 服务器无法登录的情况

https://github.com/yihong0618/MiService/issues/2

大概意思是小米是采用WLS，即无限局域网形式连接的小爱同学，服务器部署可申请api。
