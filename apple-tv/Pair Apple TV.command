#!/bin/zsh
ssh -o BatchMode=yes jhewes@192.168.0.146 '/home/jhewes/tv-favourites-venv/bin/python /home/jhewes/watch-appletv/pair.py'
printf '\nEnter this code in Watch on your Apple TV.\nPress Return to close.\n'
read
