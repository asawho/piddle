# SMTP/Text configuration, see https://docs.python.org/3/library/logging.handlers.html
# Example is given for using send grid
mailhost=('smtp.sendgrid.net', 587)
fromaddr='glass@rollingblueglass.com'
toaddrs=['where@domain.com']
credentials=('apikey','GET THIS FROM THEM')
secure=() #This means use TLS
