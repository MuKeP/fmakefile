
import sys
import logging

from .makefile import ProjectParser

__version__ = '0.2a'
__author__ = 'Anton Zakharov'


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)-15s %(levelname)8s: %(name)s(%(lineno)4s): %(message)s',
                    datefmt="%Y-%m-%d %H:%M:%S",
                    handlers=[logging.StreamHandler(sys.stdout)])
