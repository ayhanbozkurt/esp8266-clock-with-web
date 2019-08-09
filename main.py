import machine
from esp8266_i2c_lcd import I2cLcd
from bmp180 import BMP180
import time
import utime
import network
import ntptime
import usocket as socket

import esp
esp.osdebug(None)

import gc
gc.collect()

global epoch
global nextsync
epoch = 0

ntptime.NTP_DELTA = ntptime.NTP_DELTA-10800	# GMT+3
	
sta = network.WLAN(network.STA_IF)
sta.active(True)
ap = network.WLAN(network.AP_IF)
ap.active(False)


buzzer = machine.Pin(15, machine.Pin.OUT)

buzzer.off()

red  = machine.Pin(12, machine.Pin.OUT)
blue = machine.Pin(13, machine.Pin.OUT)
green = machine.Pin(14, machine.Pin.OUT)

red.off()
blue.off()
green.off()

i2c =  machine.I2C(scl=machine.Pin(4), sda=machine.Pin(5), freq=50000)
lcd = I2cLcd(i2c, 0x27, 2, 16)
lcd.custom_char(0, bytearray([0x04,0x0E,0x1B,0x0E,0x04,0x00,0x00,0x00]))

bmp180 = BMP180(i2c)
bmp180.oversample_sett = 2
bmp180.baseline = 101325

pin = machine.Pin(16, machine.Pin.IN)

header = """<!DOCTYPE html>
<html>
<head>
<title>ESP Web Server</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
<h1>ESP Web Server</h1>"""
footer = """</body></html>"""

def waitWiFi():
	sta.active(True)
	sta.connect()
	while not sta.isconnected():
		time.sleep_ms(500)
		red.on()
		time.sleep_ms(500)
		red.off()
	
def waitNTP():
	global epoch
	global nextsync
	sync=False
	while not sync:
		try:
			epoch=ntptime.time()
			sync=True
		except OSError:
			time.sleep_ms(500)
			green.on()
			time.sleep_ms(500)
			green.off()
	nextsync = epoch + 86400
	sta.active(False)
			
def handleInterrupt0(timer0):
	global epoch
	epoch += 1
	z=utime.localtime(epoch)
	lcd.move_to(0,0)
	lcd.putstr("%02d/%02d   %02d:%02d:%02d" %(z[2],z[1],z[3],z[4],z[5]))

def handleInterrupt1(timer1):
	lcd.move_to(0,1)
	v2=bmp180.temperature
	v3=bmp180.pressure
	lcd.putstr("%+.1f\0C %4d hPa" %(v2,v3/100))

def web_page(SSID_cnt, SSID_list):
	html = header + "<p>Number of Stations: <strong>"+ str(SSID_cnt) + """</strong></p>
	<p>Select SSID</p>
	<form method="get">""" + SSID_list + """<p><input type="submit" value="Submit"></p>
	</form>""" + footer
	return html
	
def web_page_get_password(SSID):
	html = header + """<p>Enter Password for <strong>""" + SSID + """</strong></p>
	<form action="" method="get">
	<p><input type="text" name="SSIDpass"></p>
	<p><input type="submit" value="Submit"></p>
	</form>""" + footer
	return html
	
def web_page_got_password(SSID,PASSWORD):
	html = header + "Password for " + SSID + " is " + PASSWORD + """<br><br>
	Configuring network...<br>
	Reboot to start clock...<br>"""+ footer 
	return html

if not pin.value():
	ap.active(True)
	if not ap.config('essid') == 'saat':
		ap.config(essid='saat')
		ap.config(password='abcd1234')

	lcd.putstr(' saat abcd1234\n '+ap.ifconfig()[0])
	
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.bind(('', 80))
	s.listen(5)

	sta = network.WLAN(network.STA_IF)
	sta_list = sta.scan()
	sta_cnt = len(sta_list)
	z = ""
	for i in range (0, sta_cnt):
		z += "<input type=\"radio\" name=\"SSIDnum\" value=\"" + "%02d"%i + "\">" + sta_list[i][0].decode() + "</br>" 
	
	gotPass = False
	
	while True:
		conn, addr = s.accept()
		print('Got a connection from %s' % str(addr))
		request = conn.recv(2048)
		request = str(request)
		print('Content = %s' % request)
		locnum  = request.find('SSIDnum=')
		locpass = request.find('SSIDpass=')
		if locnum >= 0:
			sta_id = int(request[locnum+8:locnum+10])
			sta_name = sta_list[sta_id][0].decode()
			response = web_page_get_password(sta_name)
		if (locpass >= 0) and (not gotPass):
			gotPass = True
			sta_pass = request[locpass+9:request.find(' ',locpass)]
			i = 0
			while not i==-1:
				i = sta_pass.find('%',i)
				if not i==-1:
					sta_pass = sta_pass[0:i] + chr(int(sta_pass[i+1:i+3],16)) + sta_pass[i+3:]
					i = i+1
			response = web_page_got_password(sta_name, sta_pass)
			sta.connect(sta_name, sta_pass)
		if (locnum == -1) and (locpass == -1):
			response = web_page(sta_cnt,z)
		conn.send('HTTP/1.1 200 OK\n')
		conn.send('Content-Type: text/html\n')
		conn.send('Connection: close\n\n')
		conn.sendall(response)
		conn.close()
	
else:
	lcd.putstr("System is up...\nWaiting for WiFi")

	waitWiFi()

	lcd.clear()
	lcd.putstr(str(sta.ifconfig()[0])+"\nGetting clock...")

	waitNTP()

	lcd.clear()
	timer0 = machine.Timer(0)
	timer0.init(period=1000, mode=machine.Timer.PERIODIC, callback=handleInterrupt0)

	timer1 = machine.Timer(1)
	handleInterrupt1(timer1)	# call once to get temp and pres displayed at startup
	timer1.init(period=10000, mode=machine.Timer.PERIODIC, callback=handleInterrupt1)
	
	while True:
		if epoch > nextsync:
			waitWiFi()
			waitNTP()
		time.sleep(10)		
