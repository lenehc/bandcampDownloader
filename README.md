## Overview

Given a file containing urls, the program either downloads the album if it can, or sends the album to a given email address if possible, only works for free items (May not work on WSL due to incompatibility issues with Python Selenium).

## Usage

```
$ bcdownloader.py [-h] [filename] [chromedriver-path] [-e email-address] [-f file-format]
```

## Example of url file

```
https://haircutsformen.bandcamp.com/              #To get an entire discography
https://haiructsformen.bandcamp.com/album/--2     #To get a specific album
haircutsformen.bandcamp.com/album/--2             #Invalid
/album/--2                                        #Invalid
https://haircutsformen.bandcamp.com               #Invalid
```
