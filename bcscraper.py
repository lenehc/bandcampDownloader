import os
import argparse

from re import fullmatch
from glob import glob
from json import loads
from requests import get
from time import sleep
from bs4 import BeautifulSoup as bs
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from random import randint


DOWNLOAD_LIMIT = 125


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
        html = get(self.url).content.decode('utf-8')
        doc = bs(html, 'html.parser')
        tag = doc.find("script", {data_field: True})
        json_data = loads(tag[data_field])
        return json_data

    def _get_element(self, driver, locate_by, ref):
        wait = WebDriverWait(driver, 20)
        if locate_by == 'xp':
            return wait.until(
                EC.visibility_of_element_located((By.XPATH, ref))
            )
        if locate_by == 'css':
            return wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ref))
            )
        if locate_by == 'id':
            return wait.until(
                EC.visibility_of_element_located((By.ID, ref))
            )
    
    def download(self, driver, email_address='', postal_code='95014'):
        download_link_ref = "button.download-link.buy-link"
        email_button_ref = "//div[@id='downloadButtons_email']/div/button"
        free_download_ref = "a.download-panel-free-download-link"
        download_button_ref = "//a[@data-bind='attr: { href: downloadUrl }, visible: downloadReady() && !downloadError()']"

        if self.download_url:
            driver.get(self.download_url)
            self._get_element(driver, 'xp', download_button_ref).click()

        elif self.email_required and self.is_free and email_address:
            driver.get(self.url)
            self._get_element(driver, 'css', download_link_ref).click()
            self._get_element(driver, 'id', "userPrice").send_keys("0")
            self._get_element(driver, 'css', free_download_ref).click()
            self._get_element(driver, 'id', "fan_email_address").send_keys(email_address)
            self._get_element(driver, 'id', "fan_email_postalcode").send_keys(postal_code)
            self._get_element(driver, 'xp', email_button_ref).click()


class BandcampScraper():
    def __init__(self, urls):
        self.chromedriver_path = self._get_chromedriver_path()
        self.download_path = self._get_download_path()
        self.driver = self._run_chromedriver()

        self.tralbums = {}

        print('Fetching data')

        for url in urls:
            print(f'  Fetching data from "{url}" ... ', end='\r')
            tralbum = Tralbum(url)
            print(f'  Fetching data from "{url}" ... done')
            self.tralbums[tralbum.id] = tralbum

        print(f'Fetched {len(self.tralbums)} item(s)')

        self.no_download_url_tralbums = []
        self.free_download_tralbums = list(filter(self._is_free_download, self.tralbums))
        self.email_required_tralbums = list(filter(self._is_email_required, self.tralbums))
        self.paid_tralbums = list(filter(self._is_paid, self.tralbums))
    
    def _run_chromedriver(self):
        prefs = {'download.default_directory' : self.download_path}
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_experimental_option('prefs', prefs)
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        service = Service(self.chromedriver_path)
        driver = webdriver.Chrome(options=options, service=service)
        return driver

    def _is_free_download(self, tralbum_id):
        tralbum = self.tralbums[tralbum_id]
        if tralbum.download_url:
            return True
        return False

    def _is_email_required(self, tralbum_id):
        tralbum = self.tralbums[tralbum_id]
        if tralbum.email_required and tralbum.is_free:
            return True
        return False
    
    def _is_paid(self, tralbum_id):
        tralbum = self.tralbums[tralbum_id]
        if not tralbum.is_free:
            return True
        return False

    def _is_downloaded(self, tralbum_id):
        tralbum = self.tralbums[tralbum_id]
        sleep(3)
        while True:
            sleep(1)
            if glob(f'{tralbum.artist} - {tralbum.title}*.crdownload'):
                continue
            return True

    def _get_email_address(self):
        email_address = input('(Enter email address) ')
        regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"
        
        if fullmatch(regex, email_address):
            return email_address

        print("Invalid email address")
        return self._get_email_address()

    def _get_email_source(self):
        path = input('(Enter path to email source document) ')

        if os.path.exists(path) and path.endswith(".html"):
            return os.path.abspath(path)

        print("Invalid html document")
        return self._get_email_source()

    def _get_chromedriver_path(self):
        path = input('(Enter path to chromedriver.exe) ')

        if os.path.exists(path) and os.path.basename(path) == 'chromedriver.exe':
            return os.path.abspath(path)

        print("Invalid path")
        return self._get_chromedriver_path()

    def _get_download_path(self):
        while True:
            base = f'bandcamp-scraper_{randint(1000000,9999999)}'
            path = os.path.join(os.getcwd(), base)
            if not os.path.exists(path):
                return path

    def _confirm_download(self):
        print(f'{len(self.email_required_tralbums)} of {len(self.tralbums)} item(s) require an email address to download:')
        self.print_tralbums(self.email_required_tralbums)

        while True:
            conf = input('(Download email required items? [Y/n]) ')
            if conf == "Y":
                return True
            elif conf == "n":
                return False
    
    def print_tralbums(self, tralbum_ids):
        for tralbum_id in tralbum_ids:
            tralbum = self.tralbums[tralbum_id]
            det = f'by "{tralbum.artist}"'
            if tralbum.type == 'track' and tralbum.album_title:
                det = f'from "{tralbum.album_title}" {det}'
            print(f'  "{tralbum.title}" ({det})')
    
    def send_tralbum_emails(self):
        email_address = self._get_email_address()
        print('Sending item emails')

        for tralbum_id in self.email_required_tralbums:
            tralbum = self.tralbums[tralbum_id]
            print(f'  Sending email for {tralbum.type} "{tralbum.title}" ... ', end='\r')
            tralbum.download(self.driver, email_address)
            print(f'  Sending email for {tralbum.type} "{tralbum.title}" ... done')

    def parse_email_source(self):
        email_source = self._get_email_source()
        doc = bs(open(email_source, encoding='utf-8'), 'html.parser')
        url_pattern = "a[href^='http://bandcamp.com/download?from=email&id={}&payment_id=']"

        for tralbum_id in self.email_required_tralbums:
            tralbum = self.tralbums[tralbum_id]
            download_url = doc.select_one(url_pattern.format(tralbum_id))
            if not download_url:
                self.no_download_url_tralbums.append(tralbum_id)
                continue
            tralbum.download_url = download_url['href']

    def download_tralbums(self):
        print('Downloading albums')
        os.mkdir(self.download_path)
        for tralbum_id in self.tralbums:
            tralbum = self.tralbums[tralbum_id]
            if tralbum.download_url:
                os.chdir(self.download_path)
                print(f'  Downloading {tralbum.type} "{tralbum.title}" ... ', end='\r')
                tralbum.download(self.driver)
                if self._is_downloaded(tralbum_id):
                    print(f'  Downloading {tralbum.type} "{tralbum.title}" ... done')

    def run(self):
        if self.free_download_tralbums:
            print(f'{len(self.free_download_tralbums)} of {len(self.tralbums)} item(s) are free to download:')
            self.print_tralbums(self.free_download_tralbums)

        if self.paid_tralbums:
            print(f'{len(self.paid_tralbums)} of {len(self.tralbums)} item(s) are not free to download:')
            self.print_tralbums(self.paid_tralbums)
            if len(self.paid_tralbums) == len(self.tralbums):
                return

        if self.email_required_tralbums:
            if self._confirm_download():
                self.send_tralbum_emails()
                print('Parsing email source ... ', end='\r')
                self.parse_email_source()
                print('Parsing email source ... done')

                if self.no_download_url_tralbums:
                    print(f'Could not find download url for {len(self.no_download_url_tralbums)} of {len(self.tralbums)} items:')
                    self.print_tralbums(self.no_download_url_tralbums)
                    if len(self.no_download_url_tralbums) == len(self.tralbums):
                        return
                else:
                    print('Found all download urls')
            else:
                if not self.free_download_tralbums:
                    return
                
        self.download_tralbums()

        
def is_valid_url(url):
    regex = '^(http|https)://[a-zA-Z0-9][a-zA-Z0-9\-]+[a-zA-Z0-9].bandcamp.com/(((album|track)/[a-zA-Z0-9\-]+)|music)$'
    if not fullmatch(regex, url):
        return False
    returned_status_code = get(url, allow_redirects=False).status_code     
    if not returned_status_code == 200:
        return False
    return True


def get_discog(discog_url):
    doc = bs(get(discog_url).content, 'html.parser')
    album_grid = doc.select("li.music-grid-item")
    urls = []

    for item in album_grid:
        url = f"{discog_url[:-6]}{item.a['href']}"
        urls.append(url)

    return urls
        
        
def parse_file(file, parser):
    print(f'Parsing "{file.name}"')
    urls = []
    lines = [a.strip() for a in file.readlines()]
    for line in lines:
        if not line:
            continue
        print(f'  Validating "{line}" ... ', end='\r')
        if not is_valid_url(line):
            print(f'  Validating "{line}" ... invalid')
            parser.error('invalid file contents')
        print(f'  Validating "{line}" ... valid')
        if line.endswith('/music'):
            print(f'  Getting discography from "{line}" ... ', end='\r')
            urls = urls + get_discog(line)
            print(f'  Getting discography from "{line}" ... done')
        else:
            urls.append(line)
        if len(urls) > DOWNLOAD_LIMIT:
            parser.error(f'found more than {DOWNLOAD_LIMIT} urls in file, limit exceeded')
            return

    urls = list(dict.fromkeys(urls))
    print(f'Validated {len(urls)} url(s)')
    return urls
        

def main():
    prog = 'bcscraper.py'
    usage = f'{prog} [filename]'
    
    parser = argparse.ArgumentParser(prog=prog, usage=usage)
    parser.add_argument('filename', type=argparse.FileType('r'), metavar='FILENAME', help='name of file containing track or album urls')
    args = parser.parse_args()
    
    if len(vars(args)) == 1:
        urls = parse_file(args.filename, parser)
        BandcampScraper(urls).run()


if __name__ == "__main__":
    main()
