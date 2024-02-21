import argparse
import logging
import time

from tqdm.auto import tqdm

parser = argparse.ArgumentParser(description='Steam Parser', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-a', '--above', type=int, help='The upper limit of the parsing list, default: max')
parser.add_argument('-b', '--below', type=int, help='The lower limit of the parsing list, default: 0')
parser.add_argument('-q', '--quantity-write', type=int,
                    help='Which quantity parsing entry for writing json file, default: 1000')
parser.add_argument('-f', '--file', action='store_true',
                    help='Flag for getting the entries from the last parsing json file, default: takes from url request')

logging.basicConfig(filename='logs.log', encoding='utf-8',
                    format='%(asctime)s %(message)s', datefmt='%d-%m-%Y %H:%M:%S', level=logging.INFO)


if __name__ == '__main__':
    args = parser.parse_args()
    config = vars(args)

    for i1 in tqdm(range(300), desc='main', position=0):
        for i2 in tqdm(range(300), desc='inner', position=1, leave=False):
            time.sleep(0.01)
        time.sleep(5)
