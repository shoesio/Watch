#!/usr/bin/env python3
import getpass
from five_provider import FiveAccount, FiveLoginError
print('Connect Channel 5 to Watch\nYour password is used for sign-in only; only the resulting session is saved on the Pi.\n')
try:
    email=input('Channel 5 email: ').strip()
    password=getpass.getpass('Channel 5 password (hidden): ')
    account=FiveAccount('/home/jhewes/tv-favourites-private')
    account.login(email,password)
    del password
    selected=account.lists()
    print('Connected. Found %d favourite/recent shows.' % len(selected))
    print('The next catalogue refresh will import supported shows. Playback checks must pass before Channel 5 appears on the TV.')
except KeyboardInterrupt:print('\nCancelled.')
except FiveLoginError as error:
    print(str(error))
    print('Please report this diagnostic line; it contains no email, password or token.')
except Exception as error:
    print('Diagnostic: ' + type(error).__name__)
    print('Channel 5 could not finish connecting. Check the email/password and that the account works on channel5.com. No other provider was changed.')
