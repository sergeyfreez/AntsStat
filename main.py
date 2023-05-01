import base64
import json
import log_config
import logging
import os
import re
from datetime import datetime, timedelta

import telebot
from dotenv import load_dotenv
from requests import post
from db import Ants, Stats, WildCreature, RawTexts
from spelling import spell_check

cur_dir = os.path.dirname(os.path.realpath(__file__))
log = logging.getLogger(__name__)


def image_base64_to_text(image_data):
    vision_url = os.environ.get('IMG_TO_TEXT_API_URL')
    oauth_token = os.environ.get('IMG_TO_TEXT_API_TOKEN')
    folder_id = os.environ.get('IMG_TO_TEXT_FOLDER_ID')
    response = post(vision_url, headers={'Authorization': 'Api-Key ' + oauth_token}, json={
        'folderId': folder_id,
        'analyzeSpecs': [
            {
                'content': image_data,
                'features': [
                    {
                        'type': 'TEXT_DETECTION',
                        'textDetectionConfig': {'languageCodes': ['en', 'ru']}
                    }
                ],
            }
        ]})

    def find_values(id, json_repr):
        results = []

        def _decode_dict(a_dict):
            try:
                results.append(a_dict[id])
            except KeyError:
                pass
            return a_dict

        json.loads(json_repr, object_hook=_decode_dict)  # Return value ignored.
        return results

    text = ' '.join(find_values('text', response.text))

    return text


def get_stats_from_text(text):
    lines = text.split('#')[1:]
    stat = dict()
    for line in lines:
        line = line.replace(",", "")  # '744 (BaS)Black Sins 3,140,163,399 '
        res = re.search(r'\((\w{3})\)\D*?(\d+)', line)
        if res:
            alliance_code = res.group(1)
            kills = res.group(2)
            kills = int(kills)
            stat[alliance_code] = kills
        else:
            log.warning("Can't parse " + line)

    return stat


def get_stat_diff(user_id):
    stat_diff = {}
    with open(os.path.join(cur_dir, 'stats.txt')) as f:
        history_stats = [json.loads(line.rstrip()) for line in f if json.loads(line.rstrip())['user_id'] == user_id]

    if len(history_stats) < 2:
        return None
    history_stats.sort(key=lambda x: x['date'])

    stat_diff['prev_stat'] = history_stats[-2]['date']
    prev_stat, last_stat = history_stats[-2:]
    stat_diff['interval_sec'] = last_stat['date_sec'] - prev_stat['date_sec']
    prev_stat, last_stat = prev_stat['stats'], last_stat['stats']
    diff = {}
    for alliance in last_stat.keys():
        diff[alliance] = last_stat[alliance] - prev_stat.get(alliance, 0)
    stat_diff['diff'] = diff
    return stat_diff


def format_diff(stat_diff):
    if stat_diff is None:
        return 'Не найдены первоначальные данные\nНужно больше данных'

    result = f'''Сравнение с {stat_diff['prev_stat']}
Прошло {str(timedelta(seconds=stat_diff['interval_sec']))}\n\n'''
    for alliance, diff in sorted(stat_diff['diff'].items(), key=lambda x: x[1], reverse=True):
        result += f'<code>{alliance}: {diff:14,d}</code>\n'

    return result


def process_text(text, message, bot):
    log.info(text)

    if "Рейтинг Убийств Альянса (Сезон)" in text:
        get_kill_stats(bot, message, text)
    elif "Запись о получении Оранжевых Спец" in text:
        get_orange_ants(bot, message, text)
    elif "Журнал Оранжевых Существ" in text:
        get_wild_creatures(bot, message, text)


def get_orange_ants(bot, message, text):
    results = re.findall(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(.*?)(?=(?=\d{4}-\d{2}-\d{2})|(?=$))', text)
    for dt, line in results:
        line = line.strip().replace('-', ' ').lower()
        dt = datetime.fromisoformat(dt + '+00:00').timestamp()
        if line == '':
            continue
        res = re.match(r'из за муравья(.+?), получил\(.\) (.+?)$', line)
        if res is None:
            bot.send_message(message.from_user.id, f'Can\'t parse: {line}')
            log.warning(f"Can't parse {line}")
        else:
            Ants.update_ant(
                dt=dt,
                ant=res.group(2).strip(),
                type=res.group(1).strip()
            )


def parse_creature_line(dt, line):
    line = line.replace('-', ' ').lower().strip()

    if line == '':
        return -1
    elif 'для прорыва' in line:
        return -1
    elif 'для быстрого повышения' in line:
        return -1
    elif 'получено' in line:
        res = re.match(r'в результате (.+?) получено. (.+?) ?\(.*?(\d+).*', line)

        if res and int(res.group(3)) < 10:
            if WildCreature.get_or_none(dt=dt, type=res.group(1),
                                        creature=spell_check(res.group(2)),
                                        creature_level=res.group(3)):
                return -1
            WildCreature.update_creature(
                dt=dt,
                type=res.group(1),
                creature=res.group(2),
                creature_level=res.group(3)
            )
            return 1
    elif 'неудачное повышение звезды' in line:
        if WildCreature.get_or_none(type='неудачное повышение звезды', dt=dt):
            return -1
        res = re.match(
            r'(неудачное повышение звезды) (.+?) \(.*?(\d+).*[,\.] (.+?) ?\(.*?(\d+).*деградировал',
            line)
        if res and int(res.group(3)) < 11:
            WildCreature.update_creature(
                dt=dt,
                type=res.group(1),
                creature=res.group(2),
                creature_level=res.group(3),
                donor_creature=res.group(4),
                donor_creature_level=res.group(5),
            )
            return 1
    elif 'успешное повышение звезды' in line:
        if WildCreature.get_or_none(type='успешное повышение звезды', dt=dt):
            return -1
        res = re.match(r'(успешное повышение звезды) (.+?) ?\(.*?(\d+).*? потрачено. (.+?) ?\(.*?(\d+).*', line)
        if res and int(res.group(3)) < 11 and int(res.group(5)) < 10:
            WildCreature.update_creature(
                dt=dt,
                type=res.group(1),
                creature=res.group(2),
                creature_level=res.group(3),
                donor_creature=res.group(4),
                donor_creature_level=res.group(5),
            )
            return 1
    return 0


def get_wild_creatures(bot, message, text):
    log.debug(text)
    results = re.findall(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(.*?)(?=(?=\d{4}-\d{2}-\d{2})|(?=$))', text)
    for dt, line in results:
        log.debug(f'parsing {dt}=={line}')
        raw_dt = dt
        dt = datetime.fromisoformat(dt + '+00:00').timestamp()
        parsed = parse_creature_line(dt, line)

        if parsed == 0:
            bot.send_message(message.from_user.id, f'Can\'t parse: {line}')
            log.warning(f"{message.date}_{message.from_user.id}.jpg Can't parse {raw_dt}  {line}")
        if parsed > -1:
            RawTexts.create(
                dt=dt,
                message=line,
                type='creature',
                file_path=f'{message.date}_{message.from_user.id}.jpg',
                parsed=bool(parsed)
            )


def get_kill_stats(bot, message, text):
    stats = get_stats_from_text(text)
    log.info(f'{message.from_user.id} {message.from_user.username} {message.date}')
    new_line = {
        'date_sec': message.date,
        'date': datetime.fromtimestamp(message.date).strftime('%Y-%m-%d %H:%M:%S'),
        'user_id': message.from_user.id,
        'username': message.from_user.username,
        'stats': stats
    }
    for alliance, kills in stats.items():
        Stats.create(
            dt=message.date,
            user_id=message.from_user.id,
            alliance=alliance,
            username=message.from_user.username,
            kills=kills,
        )

    with open(os.path.join(cur_dir, "stats.txt"), 'a') as f:
        f.write(json.dumps(new_line))
        f.write('\n')
    diff = get_stat_diff(message.from_user.id)
    bot.send_message(message.from_user.id, format_diff(diff), parse_mode='HTML')


def main():
    load_dotenv()
    log.info('start bot')
    bot = telebot.TeleBot(os.environ.get('TG_TOKEN'))
    bot.send_message(os.environ.get('TG_CHAT_ID'), 'hello')

    @bot.message_handler(content_types=['photo'])
    def get_photo_messages(message):
        file_id = message.photo[-1].file_id
        log.info('file_id =' + file_id)
        file_info = bot.get_file(file_id)

        downloaded_file = bot.download_file(file_info.file_path)
        image_data = base64.b64encode(downloaded_file).decode('utf-8')
        with open(os.path.join(cur_dir, 'img', f'{message.date}_{message.from_user.id}.jpg'), 'wb') as new_file:
            new_file.write(downloaded_file)
        text = image_base64_to_text(image_data)

        process_text(text, message, bot)

    bot.polling(none_stop=True, interval=0)


if __name__ == '__main__':
    main()
