from machine import Pin, I2C
import ssd1306
import network
import urequests as requests
import time

# Her Konfigurer vores I2C og skriver de pins vi bruger
i2c = I2C(-1, scl=Pin(22), sda=Pin(21))

def init_oled():
    global oled
    try:
        oled = ssd1306.SSD1306_I2C(128, 64, i2c)
        oled.fill(0)
        oled.show()
        print("oled skærm forbundet")
    except Exception as e:
        print("Kan ikke forbinde til oled skærm:", e)

# Konfigurer vores taktile tryk knap, og vælger den pin vi bruger
button_pin = 14
button = Pin(button_pin, Pin.IN, Pin.PULL_UP)

# Her er vores Variabel til at holde styr på om vores skærm er tændt eller ej. Ved opstart starter vores oled skærm altid med at være slukket
screen_on = False
last_press_time = 0

# Her har vi en funktion som gør at vi kan oprette forbindelse til vores wifi. 
def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Opretter forbindelse til wifi')
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            pass
    print('Forbundet til wifi:', ssid)

# EN funktion som henter vores 2FA kode fra vores flask server og viser så 2FA koden på displayet
def get_and_display_tfa_code(flask_url):
    try:
        response = requests.get(flask_url + '/get_tfa_code')
        if response.status_code == 200:
            data = response.json()
            tfa_code = data.get('tfa_code')
            if tfa_code:
                oled.fill(0) 
                oled.text("2FA Kode:", 20, 10, 1)
                oled.text(tfa_code, 30, 30, 1)
                oled.show()
                print("Modtaget 2fa koden", tfa_code)
            else:
                print("Fejl ved 2fa koden")
        else:
            print("Kan ikke forbinde til flask server", response.status_code)
    except Exception as e:
        print("fejl:", e)

# Funktion til at vi kan toggle vores oled skærm
def toggle_screen(pin):
    global screen_on, last_press_time
    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, last_press_time) > 200: 
        screen_on = not screen_on
        if screen_on:
            print("Tænder skærm")
            get_and_display_tfa_code("http://192.168.8.10:5000") # vores ip og port nr på vores flask server
        else:
            oled.fill(0)
            oled.show()
            print("Slukker skærmen")
        last_press_time = current_time
# Funktion til få navnet på vores wifi, koden og url til vores flask server 
def main():
    ssid = "Homesite" # Vores wifi ssid
    password = "Tvglad1234" # Vores wifi kode
    flask_url = "http://192.168.8.10:5000"  # Vores flask server ip og port
    
    init_oled()
    connect_wifi(ssid, password)
    
    button.irq(trigger=Pin.IRQ_FALLING, handler=toggle_screen)
    
    while True:
        if screen_on:
            get_and_display_tfa_code(flask_url)
        time.sleep(1)  # Opdaterer vores 2fa kode hvert sekundt, så når der kommer en ny vises den på skærmen

if __name__ == "__main__":
    main()
