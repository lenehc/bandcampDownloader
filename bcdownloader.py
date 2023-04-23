import os
import argparse
import re
import requests
import logging

from glob import glob
from time import sleep
from sys import exit
from json import loads
from time import gmtime, strftime
from bs4 import BeautifulSoup as bs
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


DOWNLOAD_ABORT_LIMIT = 180

DOWNLOADED, EMAIL, FAILED = 0, 0, 0

FILE_FORMATS = ['mp3-v0','mp3-320','flac','aac-hi','vorbis','alac','wav','aiff-lossless']

DOWNLOAD_PATH = os.path.join(os.getcwd(), f'bcscraper_{strftime("%Y%m%d%H%M%S", gmtime())}')
STATUS = '{} downloaded, {} email required, {} failed'

ARTIST_URL_PATTERN = re.compile(r'^https://[a-zA-z0-9\-]+.bandcamp.com/$')
TRALBUM_FULL_URL_PATTERN = re.compile(r'^https://[a-zA-z0-9\-]+.bandcamp.com/(track|album)/[a-zA-Z0-9\-]+$')
TRALBUM_URL_PATTERN = re.compile(r"^/(album|track)")

DOWNLOAD_LINK_REF = "button.download-link.buy-link"
EMAIL_BUTTON_REF = "#downloadButtons_email > div:nth-child(1) > button:nth-child(1)"
FREE_DOWNLOAD_REF = "a.download-panel-free-download-link"
DOWNLOAD_BUTTON_REF = "div.download-format-tmp > a:nth-child(5)"


class BandcampDownloader():
    '''
    Main class for downloader
    '''

    def __init__(self, file, chromedriver_path, email_address, file_format):
        self.urls = self._parse_file(file)
        self.driver = self._run_chromedriver(chromedriver_path)
        self.email_address = email_address
        self.file_format = file_format

    def _get_tralbum_info(self, url):
        '''
        Get tralbum info from page html. Extract relevant data to
        dict element
        '''
        doc = bs(requests.get(url).content.decode('utf-8'), 'html.parser')
        tag = doc.find("script", {'data-tralbum': True})
        data = loads(tag['data-tralbum'])

        info = {}
        info['download_url'] = data['freeDownloadPage']
        info['is_free'] = True if data['current']['minimum_price'] == 0 else False
        info['email_required'] = bool(data['current']['require_email']) 
        info['is_downloadable'] = True

        if data['current']['type'] == 'track':
            info['is_downloadable'] = data['trackinfo'][0]['is_downloadable']

        return info

    def _run_chromedriver(self, chromedriver_path):
        '''
        Start Chromedriver, return webdriver object
        '''
        prefs = {'download.default_directory' : DOWNLOAD_PATH}
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_experimental_option('prefs', prefs)
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        service = Service(chromedriver_path)
        driver = webdriver.Chrome(options=options, service=service)

        return driver

    def _get_element(self, ref):
        '''
        Wait for visibility of element
        '''
        wait = WebDriverWait(self.driver, 20)

        return wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ref)))

    def _get_artist_urls(self, url):
        '''
        Parse artist discography page for album and track urls
        '''
        doc = bs(requests.get(url + 'music').content, 'html.parser')
        urls = doc.find_all("a", href=TRALBUM_URL_PATTERN)

        return [f"{url[:-1]}{a['href']}" for a in urls]

    def _parse_file(self, file):
        '''
        Iterate over file and log error if line is invalid
        '''
        urls = []

        for i,line in enumerate(file):
            url = line.strip()
            if ARTIST_URL_PATTERN.search(url):
                try:
                    urls = urls + self._get_artist_urls(url)
                except TypeError:
                    logging.error(f'invalid artist url at line {i+1}')
                    exit(1)
            elif TRALBUM_FULL_URL_PATTERN.search(url):
                try:
                    requests.get(url).raise_for_status()
                    urls.append(url)
                except requests.exceptions.HTTPError:
                    logging.error(f'invalid item url at line {i+1}')
                    exit(1)
            else:
                logging.error(f'invalid url at line {i+1}')
                exit(1)

        return list(set(urls))
 
    def _is_download(self):
        '''
        Continuously iterate over download dir until no *.crdownload
        or *.tmp files are found, return false after 3 minutes
        '''
        sleep(1)

        for i in range(DOWNLOAD_ABORT_LIMIT):
            sleep(1)
            if not glob('*.crdownload') or glob('*.tmp'):
                return True
        return False

    def get_tralbum(self, url):
        '''
        Download tralbum or send email to email address
        '''
        global DOWNLOADED, EMAIL, FAILED
        info = self._get_tralbum_info(url)

        if info['download_url'] and info['is_downloadable']:
            self.driver.get(info['download_url'])
            if self.file_format:
                select = Select(self._get_element("#format-type"))
                select.select_by_value(self.file_format)
            self._get_element(DOWNLOAD_BUTTON_REF).click()
            if self._is_downloaded():
                DOWNLOADED += 1
                print(f'  DOWNLOADED  {url}')
                return

        elif info['email_required'] and info['is_downloadable'] and info['is_free']:
            EMAIL += 1
            if self.email_address:
                self.driver.get(url)
                self._get_element(DOWNLOAD_LINK_REF).click()
                self._get_element("#userPrice").send_keys("0")
                self._get_element(FREE_DOWNLOAD_REF).click()
                self._get_element("#fan_email_address").send_keys(self.email_address)
                self._get_element("#fan_email_postalcode").send_keys('95014')
                self._get_element(EMAIL_BUTTON_REF).click()
                print(f'  SENT-EMAIL  {url}')
            else:
                print(f'  EMAIL-REQ   {url}')
            return
        
        FAILED += 1
        print(f'  FAILED      {url}')

    def run(self):
        '''
        Start download process
        '''
        os.mkdir(DOWNLOAD_PATH)
        os.chdir(DOWNLOAD_PATH)

        for i,url in enumerate(self.urls):
            print(f'Fetching: {i+1} of {len(self.urls)}', end='\r')
            self.get_tralbum(url)

        print(f'\nFetched {len(self.urls)} item(s)')
        print(STATUS.format(DOWNLOADED, EMAIL, FAILED))
        

def chromedriver_path(path):
    '''
    Argparse type function for chromedriver path
    '''
    if os.path.exists(path) and os.path.basename(path) == 'chromedriver.exe':
        return path

    raise argparse.ArgumentTypeError('invalid chromedriver path')

    
def email_address(email_address):
    '''
    Argparse type function for email address
    '''
    regex = "([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+"

    if re.fullmatch(regex, email_address):
        return email_address

    raise argparse.ArgumentTypeError('invalid email address')
    
def file_format(format):
    '''
    Argparse type function for file format
    '''
    if format in FILE_FORMATS:
        return format

    raise argparse.ArgumentTypeError(f'invalid file format, choose from: {", ".join(FILE_FORMATS)}')

def main():
    '''
    Setup Argparse and logging and pass options to BandcampDownloader
    '''
    
    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.addLevelName(logging.ERROR, 'error')

    usage = 'bcdownloader.py [-h] [filename] [chromedriver-path] [-e email-address] [-f file-format]'
    parser = argparse.ArgumentParser(usage=usage)
    parser.add_argument('file',
                        type=argparse.FileType('r'),
                        help='input filename, one url per line')
    parser.add_argument('chromedriver_path',
                        type=chromedriver_path,
                        help='path to chromedriver.exe')
    parser.add_argument('-e', '--email-address',
                        dest="email_address",
                        type=email_address,
                        help='email address string, if omitted email required albums will not be downloaded')
    parser.add_argument('-f', '--file-format',
                        dest="file_format",
                        type=file_format,
                        help=f'file format for albums and tracks, if omitted files will be downloaded in: {FILE_FORMATS[0]}')

    args = parser.parse_args()

    BandcampDownloader(args.file, args.chromedriver_path, args.email_address, args.file_format).run()

if __name__ == '__main__':
    main()
