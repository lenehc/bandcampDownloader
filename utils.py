import time
import requests
import json

from bs4 import BeautifulSoup as bs
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

class Tralbum():
    def __init__(self, url):
        self.url = url
        self.json = self._get_json('data-tralbum')
        self.id = int(self.json['id'])
        self.title = self.json['current']['title']
        self.artist = self.json['artist']
        self.type = self.json['current']['type']
        self.email_required = bool(self.json['current']['require_email']) 
        self.download_url = self.json['freeDownloadPage']
        self.is_free = False

        if self.type == 'track':
            try:
                self.album_title = self._get_json('data-embed')['album_title']
            except KeyError: 
                self.album_title = ''

            is_downloadable = self.json['trackinfo'][0]['is_downloadable']
            if self.json['current']['minimum_price'] == 0 and is_downloadable:
                self.is_free = True

        else:
            if self.json['current']['minimum_price'] == 0:
                self.is_free = True
        
    def _get_json(self, data_field):
        html = requests.get(self.url).content.decode('utf-8')
        doc = bs(html, 'html.parser')
        tag = doc.find("script", {data_field: True})
        json_data = json.loads(tag[data_field])
        return json_data

    def download(self, driver, email_address='', postal_code='95014'):
        download_link_ref = "button.download-link.buy-link"
        email_button_ref = "//div[@id='downloadButtons_email']/div/button"
        free_download_ref = "a.download-panel-free-download-link"
        download_button_ref = "//a[@data-bind='attr: { href: downloadUrl }, visible: downloadReady() && !downloadError()']"

        if self.download_url:
            driver.get(self.download_url)
            time.sleep(5)
            driver.find_element(By.XPATH, download_button_ref).click()

        elif self.email_required and self.is_free and email_address:
            driver.get(self.url)
            driver.find_element(By.CSS_SELECTOR, download_link_ref).click() 
            driver.find_element(By.ID, "userPrice").send_keys("0")
            time.sleep(2)
            driver.find_element(By.CSS_SELECTOR, free_download_ref).click()
            driver.find_element(By.ID, "fan_email_address").send_keys(email_address)
            driver.find_element(By.ID, "fan_email_postalcode").send_keys(postal_code)
            driver.find_element(By.XPATH, email_button_ref).click()
