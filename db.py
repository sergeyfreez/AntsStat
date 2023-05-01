# -*- coding: utf-8 -*-
import datetime
import logging
import os

import psycopg2
from dotenv import load_dotenv
from peewee import *

from spelling import spell_check

import logging
log = logging.getLogger(__name__)

cur_dir = os.path.dirname(os.path.realpath(__file__))
load_dotenv()

logger = logging.getLogger('peewee')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.ERROR)

psql_db = PostgresqlDatabase(os.environ.get('POSTGRESQL_DB_NAME'),
                             host=os.environ.get('POSTGRESQL_HOST'),
                             port=int(os.environ.get('POSTGRESQL_PORT')),
                             user=os.environ.get('POSTGRESQL_USER'),
                             password=os.environ.get('POSTGRESQL_PASS'))
psql_db.connect()


class BaseModel(Model):
    """A base model that will use our Postgresql database"""

    class Meta:
        database = psql_db


class Ants(BaseModel):
    dt = TimestampField()
    ant = TextField()
    type = TextField()

    def update_ant(dt, ant, type):
        try:
            Ants.get_or_create(
                dt=dt,
                ant=spell_check(ant),
                type=spell_check(type)
            )
        except IntegrityError as e:
            print(e)
            print(dt, spell_check(ant), spell_check(type))

    class Meta:
        database = psql_db
        primary_key = CompositeKey('dt', 'ant')


class WildCreature(BaseModel):
    dt = TimestampField()
    type = TextField()
    creature = TextField()
    creature_level = SmallIntegerField()
    donor_creature = TextField(null=True)
    donor_creature_level = SmallIntegerField(null=True)

    def update_creature(dt, type, creature, creature_level, donor_creature=None, donor_creature_level=None):
        try:
            WildCreature.get_or_create(dt=dt, type=spell_check(type), creature=spell_check(creature),
                                       creature_level=creature_level,
                                       donor_creature=spell_check(donor_creature),
                                       donor_creature_level=donor_creature_level)
        except IntegrityError as e:
            print(e)
            print(dt, type, creature, creature_level, donor_creature, donor_creature_level)

    class Meta:
        database = psql_db
        primary_key = CompositeKey('dt', 'type', 'creature', 'creature_level')


class Stats(BaseModel):
    dt = TimestampField()
    user_id = IntegerField()
    alliance = TextField()
    username = TextField()
    kills = BigIntegerField()

    class Meta:
        database = psql_db
        primary_key = CompositeKey('dt', 'alliance')


class ImprovementCost(BaseModel):
    level_from = IntegerField()
    level_to = IntegerField()
    optimized_cost_success = IntegerField()
    full_cost = IntegerField()
    optimized_cost_fail = IntegerField()

    optimized_egg_success = IntegerField()
    optimized_egg_fail = IntegerField()
    full_egg = IntegerField()

    class Meta:
        database = psql_db
        primary_key = CompositeKey('level_from', 'level_to')


class RawTexts(BaseModel):
    dt = TimestampField()
    message = TextField()
    type = TextField()
    file_path = TextField()
    s3_id = TextField(null=True)
    parsed = BooleanField(default=False)


def init_db():
    psql_db.drop_tables([Stats])
    psql_db.create_tables([Stats])
    import json

    with open(os.path.join(cur_dir, 'stats.txt')) as f:
        history_stats = [json.loads(line.rstrip()) for line in f]
    for stat in history_stats:
        for alliance, kills in stat['stats'].items():
            q = Stats(
                dt=stat['date_sec'],
                user_id=stat['user_id'],
                alliance=alliance,
                username=stat['username'],
                kills=kills)

            q.save(force_insert=True)


def init_dicts():
    psql_db.drop_tables([ImprovementCost])
    psql_db.create_tables([ImprovementCost])
    with open('db_migrate/improvement_cost.csv', 'r') as f:
        next(f)
        psql_db.cursor().copy_from(f, 'improvementcost', sep=';')
    psql_db.commit()


def creature_example_check():
    import re
    from datetime import datetime
    text = '''13:19 -1 Журнал Оранжевых Существ 2023-03-14 04:54:32 В результате события получено: Скорпион (3 2023-03-12 19:53:32 В результате вылупления получено: Паук-Скакун (1 *) 2023-03-12 05:15:24 В результате покупки набора получено: Жук Атлас (2%) 2023-03-12 05:15:24 В результате покупки набора получено: Жук Атлас (1 2023-03-12 05:15:05 В результате покупки набора получено: Жук Атлас (1 2023-03-12 05:10:26 Для быстрого повышения звезды потрачены следующие Дикие Существа 2023-03-11 05:37:22 В результате события получено: Гигантский Богомол (3 2023-03-09 06:31:22 В результате использования предмета получено: Рак-Отшельник (1 2023-03-07 15:20:01 В результате вылупления получено: Скорпион (1 2023-03-05 21:20:16 В результате вылупления получено: Рак-Отшельник (1 2023-03-05 21:06:48 Неудачное повышение звезды Гигантский Богомол (9*), Скоwрпион (8*) деградировал(а) в Скорпион (7*) 2023-03-05 19:20:44 Успешное повышение звезды Скорпион (7ж), потрачено: Гигантский Богомол (6%) 2023-03-05 15:06:36 Для прорыва уровня Дикого Существа (Гигантский Богомол (9%)) потрачены следующие Дикие Существа 2023-03-05 15:06:07 Для прорыва уровня Дикого Существа (Скорпион (7*)) потрачены следующие Дикие Существа 2023-03-05 15:05:53 Для быстрого повышения звезды потрачены следующие Дикие Существа 2023-03-05 13:30:33 Для прорыва уровня Дикого Существа (Жук Атлас (7*)) потрачены следующие Дикие Существа 2023-03-05 13:29:11'''
    results = re.findall(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(.*?)(?=(?=\d{4}-\d{2}-\d{2})|(?=$))', text)
    for dt, line in results:
        line = line.strip().replace('-', ' ').lower()
        dt = datetime.fromisoformat(dt).timestamp()
        if line == '':
            pass
        elif 'для прорыва' in line:
            pass
        elif 'для быстрого повышения' in line:
            pass
        elif 'получено' in line:
            res = re.match(r'в результате (.+?) получено. (.+?) ?\(.*?(\d+).*', line)
            if res and int(res.group(3)) < 10:
                WildCreature.update_creature(
                    dt=dt,
                    type=res.group(1),
                    creature=res.group(2),
                    creature_level=res.group(3)
                )
            else:
                # bot.send_message(message.from_user.id, f'Can\'t parse: {line}')
                print("Can't parse ", line)
        elif 'неудачное повышение звезды' in line:
            res = re.match(
                r'(неудачное повышение звезды) (.+?) \(.*?(\d+).*, (.+?) ?\(.*?(\d+).*деградировал.+? в (.+?) ?\(.*?(\d+).*',
                line)
            if res and int(res.group(3)) < 10 and int(res.group(5)) < 10:
                WildCreature.update_creature(
                    dt=dt,
                    type=res.group(1),
                    creature=res.group(2),
                    creature_level=res.group(3),
                    donor_creature=res.group(4),
                    donor_creature_level=res.group(5),
                )
            else:
                # bot.send_message(message.from_user.id, f'Can\'t parse: {line}')
                print("Can't parse ", line)
        elif 'успешное повышение звезды' in line:
            res = re.match(r'(успешное повышение звезды) (.+?) ?\(.*?(\d+).*, потрачено. (.+?) ?\(.*?(\d+).*', line)
            if res and int(res.group(3)) < 10 and int(res.group(5)) < 10:
                WildCreature.update_creature(
                    dt=dt,
                    type=res.group(1),
                    creature=res.group(2),
                    creature_level=res.group(3),
                    donor_creature=res.group(4),
                    donor_creature_level=res.group(5),
                )
            else:
                # bot.send_message(message.from_user.id, f'Can\'t parse: {line}')
                print("Can't parse ", line)
        else:
            # bot.send_message(message.from_user.id, f'Can\'t parse: {line}')
            print("Can't parse ", line)


if __name__ == '__main__':
    # init_db()
    pass
    # all = Stats.select().where(Stats.user_id == 116371519).order_by(Stats.dt.desc())
    # for s in all[:8*3]:
    #     print(s)
    # print(type(all))
    # init_dicts()
    datetime.datetime.now().isoformat()
    # psql_db.drop_tables([RawTexts])
    # psql_db.create_tables([RawTexts])
    # creature_example_check()
