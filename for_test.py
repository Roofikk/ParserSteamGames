import argparse
import logging
import os.path


parser = argparse.ArgumentParser(description='Steam Parser', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-a', '--above', type=int, help='The upper limit of the parsing list, default: max')
parser.add_argument('-b', '--below', type=int, help='The lower limit of the parsing list, default: 0')
parser.add_argument('-q', '--quantity-write', type=int,
                    help='Which quantity parsing entry for writing json file, default: 1000')
parser.add_argument('-f', '--file', type=str,
                    help='Any full path to json file which was created on last parses, default: takes from url request')

logging.basicConfig(filename='logs.log', encoding='utf-8',
                    format='%(asctime)s %(message)s', datefmt='%d-%m-%Y %H:%M:%S', level=logging.INFO)


if __name__ == '__main__':
    args = parser.parse_args()
    config = vars(args)

    path = config['file']
    print(os.path.exists(path))

    f = open(path, 'r', encoding='utf-8')
    print('I opened file')
    f.close()
