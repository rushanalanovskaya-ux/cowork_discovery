#!/usr/bin/env python3
from pdlc import ROOT, read_json, score

if __name__ == '__main__':
    ranked, incomplete = [], []
    for item in read_json(ROOT, 'backlog/items.json'):
        value, error = score(item)
        if error:
            incomplete.append((item, error))
        else:
            ranked.append((item, value))
    print('RICE — сравнивать только одинаковую единицу reach и горизонт. Не является решением о scope.')
    for item, value in sorted(ranked, key=lambda pair: (-pair[1], pair[0]['id'])):
        print(f"{item['id']}\t{value:.3f}\t{item['title']}")
    print(f'Недостаточно данных: {len(incomplete)}; оценены: {len(ranked)}.')
    for item, error in incomplete:
        print(f"{item['id']}\t{item['proposed_lane']}\t{error}")
