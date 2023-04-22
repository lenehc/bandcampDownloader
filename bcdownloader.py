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


DOWNLOADED, EMAIL, FAILED = 0, 0, 0

FILE_FORMATS = ['mp3-v0','mp3-320','flac','aac-hi','vorbis','alac','wav','aiff-lossless']

DOWNLOAD_PATH = os.path.join(os.getcwd(), f'bcscraper_{strftime("%Y%m%d%H%M%S", gmtime())}')
STATUS = '\n{} downloaded items, {} email required items, {} failed items'

ARTIST_URL_PATTERN = re.compile(r'^https://[a-zA-z0-9\-]+.bandcamp.com/$')
TRALBUM_FULL_URL_PATTERN = re.compile(r'^https://[a-zA-z0-9\-]+.bandcamp.com/(track|album)/[a-zA-Z0-9\-]+$')
TRALBUM_URL_PATTERN = re.compile(r"^/(album|track)")

DOWNLOAD_LINK_REF = "button.download-link.buy-link"
EMAIL_BUTTON_REF = "//div[@id='downloadButtons_email']/div/button"
FREE_DOWNLOAD_REF = "a.download-panel-free-download-link"
DOWNLOAD_BUTTON_REF = "//a[@data-bind='attr: { href: downloadUrl }, visible: downloadReady() && !downloadError()']"
    

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

    def _get_element(self, by, ref):
        '''
        Wait for visibility of element
        '''
        wait = WebDriverWait(self.driver, 20)

        if by == 'xp':
            return wait.until(EC.visibility_of_element_located((By.XPATH, ref)))

        if by == 'css':
            return wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ref)))

        if by == 'id':
            return wait.until(EC.visibility_of_element_located((By.ID, ref)))

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
 
    def _wait_for_download(self):
        '''
        Continuously iterate over download dir until no *.crdownload
        or *.tmp files are found
        '''
        sleep(3)

        while True:
            sleep(1)
            if not glob('*.crdownload') or glob('*.tmp'):
                return

    def get_tralbum(self, url):
        '''
        Download tralbum or send email to email address
        '''
        global DOWNLOADED, EMAIL
        info = self._get_tralbum_info(url)

        if info['download_url'] and info['is_downloadable']:
            DOWNLOADED += 1
            self.driver.get(info['download_url'])
            if self.file_format:
                select = Select(self._get_element('id', "format-type"))
                select.select_by_value(self.file_format)
            self._get_element('xp', DOWNLOAD_BUTTON_REF).click()
            return

        elif info['email_required'] and info['is_downloadable'] and self.email_address:
            EMAIL += 1
            self.driver.get(url)
            self._get_element('css', DOWNLOAD_LINK_REF).click()
            self._get_element('id', "userPrice").send_keys("0")
            self._get_element('css', FREE_DOWNLOAD_REF).click()
            self._get_element('id', "fan_email_address").send_keys(self.email_address)
            self._get_element('id', "fan_email_postalcode").send_keys('95014')
            self._get_element('xp', EMAIL_BUTTON_REF).click()
            return
        
        FAILED += 1

    def run(self):
        '''
        Start download process
        '''
        os.mkdir(DOWNLOAD_PATH)
        os.chdir(DOWNLOAD_PATH)

        for i,url in enumerate(self.urls):
            print(f'Getting items - {i+1}/{len(self.urls)}', end='\r')
            self.get_tralbum(url)
            self._wait_for_download()

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
                        metavar='filename')
    parser.add_argument('chromedriver_path',
                        type=chromedriver_path,
                        metavar='chromedriver-path')
    parser.add_argument('-e', '--email-address',
                        dest="email_address",
                        type=email_address,
                        metavar='email-address')
    parser.add_argument('-f', '--file-format',
                        dest="file_format",
                        type=file_format,
                        metavar='file-format')

    args = parser.parse_args()

    BandcampDownloader(args.file, args.chromedriver_path, args.email_address, args.file_format).run()

if __name__ == '__main__':
    main()
