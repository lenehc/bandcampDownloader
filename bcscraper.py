import os
import argparse
import re

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


DOWNLOAD_LIMIT = 200


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
    def __init__(self, urls, chromedriver_path):
        self.download_path = self._get_download_path()
        self.driver = self._run_chromedriver(chromedriver_path)
        self.tralbums = {}

        print(f'Fetching {len(urls)} items')

        for url in urls:
            tralbum = Tralbum(url)
            self.tralbums[tralbum.id] = tralbum

        self.no_download_url_tralbums = []
        self.free_download_tralbums = list(filter(self._is_free_download, self.tralbums))
        self.email_required_tralbums = list(filter(self._is_email_required, self.tralbums))
        self.paid_tralbums = list(filter(self._is_paid, self.tralbums))
    
    def _run_chromedriver(self, chromedriver_path):
        prefs = {'download.default_directory' : self.download_path}
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_experimental_option('prefs', prefs)
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        service = Service(chromedriver_path)
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
        
        if re.fullmatch(regex, email_address):
            return email_address

        print("Invalid email address")
        return self._get_email_address()

    def _get_email_source(self):
        path = input('(Enter path to email source document) ')

        if os.path.exists(path) and path.endswith(".html"):
            return os.path.abspath(path)

        print("Invalid html document")
        return self._get_email_source()

    def _get_download_path(self):
        while True:
            base = f'bandcamp-scraper_{randint(1000000,9999999)}'
            path = os.path.join(os.getcwd(), base)
            if not os.path.exists(path):
                return path

    def _confirm_download(self):
        while True:
            conf = input('(Download email required items? [Y/n]) ')
            if conf == "Y":
                return True
            elif conf == "n":
                return False
    
    def print_tralbums(self, tralbum_ids, indent=2):
        for tralbum_id in tralbum_ids:
            tralbum = self.tralbums[tralbum_id]
            det = f'by "{tralbum.artist}"'
            if tralbum.type == 'track' and tralbum.album_title:
                det = f'from "{tralbum.album_title}" {det}'
            print(f'{" "*indent}"{tralbum.title}" ({det})')
    
    def send_tralbum_emails(self):
        email_address = self._get_email_address()
        print('  Sending item emails')

        for tralbum_id in self.email_required_tralbums:
            tralbum = self.tralbums[tralbum_id]
            tralbum.download(self.driver, email_address)

    def parse_email_source(self):
        email_source = self._get_email_source()
        print('  Parsing email source')
        with open(email_source, 'r', encoding='utf-8') as file:
            source = file.read().replace('&amp;', '&')
        url_pattern = 'http://bandcamp.com/download\?from=email&amp;id={}+&amp;payment_id=[0-9]+&amp;sig=[a-z0-9]+&amp;type={}'

        for tralbum_id in self.email_required_tralbums:
            tralbum = self.tralbums[tralbum_id]
            download_url = re.search(url_pattern.format(tralbum.id, tralbum.type), source)
            if not download_url:
                self.no_download_url_tralbums.append(tralbum_id)
                continue
            tralbum.download_url = download_url.group()

    def download_tralbums(self):
        os.mkdir(self.download_path)
        for tralbum_id in self.tralbums:
            tralbum = self.tralbums[tralbum_id]
            if tralbum.download_url:
                os.chdir(self.download_path)
                print(f'  Downloading {tralbum.type} "{tralbum.title}"')
                tralbum.download(self.driver)
                if self._is_downloaded(tralbum_id):
                    continue

    def run(self):
        if self.paid_tralbums:
            print(f'  {len(self.paid_tralbums)} items are not free to download:')
            self.print_tralbums(self.paid_tralbums, indent=4)
            if len(self.paid_tralbums) == len(self.tralbums):
                return

        if self.email_required_tralbums:
            print(f'  {len(self.email_required_tralbums)} items require an email address to download:')
            self.print_tralbums(self.email_required_tralbums, indent=4)
            if self._confirm_download():
                self.send_tralbum_emails()
                self.parse_email_source()

                if self.no_download_url_tralbums:
                    if len(self.no_download_url_tralbums) == len(self.tralbums):
                        print('    Could not find any download urls')
                        return
                    elif len(self.no_download_url_tralbums) == len(self.email_required_tralbums):
                        print('    Could not find any download urls')
                    else:
                        print(f'    Could not find download url for {len(self.no_download_url_tralbums)} items:')
                        self.print_tralbums(self.no_download_url_tralbums, indent=8)
            else:
                if not self.free_download_tralbums:
                    return
                
        print('Downloading albums')
        self.download_tralbums()

class ParseFile():
    def __init__(self, file, parser):
        self.file = file
        self.urls = self._get_urls(parser)

    def _is_valid_url(self, url):
        regex = '^(http|https)://[a-zA-Z0-9][a-zA-Z0-9\-]+[a-zA-Z0-9].bandcamp.com/(((album|track)/[a-zA-Z0-9\-]+)|music)$'
        if not re.fullmatch(regex, url):
            return False
        returned_status_code = get(url, allow_redirects=False).status_code     
        if not returned_status_code == 200:
            return False
        return True

    def _get_discog(self, discog_url):
        doc = bs(get(discog_url).content, 'html.parser')
        album_grid = doc.select("li.music-grid-item")
        urls = []

        for item in album_grid:
            url = f"{discog_url[:-6]}{item.a['href']}"
            urls.append(url)

        return urls

    def _get_urls(self, parser):
        urls = []
        lines = [a.strip() for a in self.file.readlines()]

        if len(lines) == 0:
            parser.error(f'found no urls in file')

        for line in lines:
            if not line:
                continue
            if not self._is_valid_url(line):
                parser.error(f'invalid file contents, "{line}" is not a valid url')
            if line.endswith('/music'):
                urls = urls + self._get_discog(line)
            else:
                urls.append(line)
            if len(urls) > DOWNLOAD_LIMIT:
                parser.error(f'found more than {DOWNLOAD_LIMIT} urls in file, limit exceeded')

        urls = list(dict.fromkeys(urls))
        return urls

    
def chromedriver_path(path):
    if os.path.exists(path) and os.path.basename(path) == 'chromedriver.exe':
        return path

    
def main():
    prog = 'bcscraper.py'
    usage = f'{prog} [filename] [chromedriver path]'
    
    parser = argparse.ArgumentParser(prog=prog, usage=usage)
    parser.add_argument('file',
                        type=argparse.FileType('r'),
                        metavar='FILE',
                        help='name of file containing track or album urls')
    parser.add_argument('chromedriver_path',
                        type=chromedriver_path,
                        metavar='CHROMEDRIVER PATH',
                        help='path to chromedriver.exe')

    args = parser.parse_args()
        
    print(f'Parsing "{args.file.name}"')
    urls = ParseFile(args.file, parser).urls

    BandcampScraper(urls, args.chromedriver_path).run()


if __name__ == "__main__":
    main()
