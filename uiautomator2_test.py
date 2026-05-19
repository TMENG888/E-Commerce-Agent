import uiautomator2 as u2

ip_port = "172.20.10.4:43387"

device = u2.connect(ip_port)

print("设备已连接")