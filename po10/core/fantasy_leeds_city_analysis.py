from po10_scraper import PowerOf10

import numpy as np
import datetime
import pandas as pd


def get_xc_results(po10, race, id, event):
    race_results = po10.get_results(meeting_id=id, event=event)[f'{event} SM']
    leeds_results = race_results[race_results['Club'].str.contains('Leeds City', na=False)].reset_index()
    leeds_results[f'{race}_pos'] = leeds_results.index + 1

    leeds_results = leeds_results[['AthleteId','Name', f'{race}_pos']]
    leeds_results[f'{race}_points'] = leeds_results[f'{race}_pos'].apply(lambda x: 25 - x if x <= 20 else 4)
    
    return leeds_results


def get_relay_results(po10, race, id, event, multi_distance=False, leg_weightings=None,
                      longleg=None, shortleg=None, time_index='Gun'):
    
    if leg_weightings is not None:
        short_weightings = [20 - i for i, x in enumerate(leg_weightings) if x == "s"]
        long_weightings = [20 - i for i, x in enumerate(leg_weightings) if x == "l"]
    
    race_results = po10.get_results(meeting_id=id, event=event)
    if multi_distance:
        long_legs, short_legs = get_long_short_legs(race_results, longleg, shortleg)
        leeds_short_legs = short_legs[short_legs['Club'].str.contains('Leeds City', na=False)].reset_index()
        leeds_long_legs = long_legs[long_legs['Club'].str.contains('Leeds City', na=False)].reset_index()
        leeds_short_legs['total_seconds'] = leeds_short_legs['Gun'].apply(get_total_seconds)
        leeds_long_legs['total_seconds'] = leeds_long_legs['Gun'].apply(get_total_seconds)
        
        leeds_long_legs = leeds_long_legs.sort_values(by=['total_seconds']).reset_index()
        leeds_short_legs = leeds_short_legs.sort_values(by=['total_seconds']).reset_index()
        
        leeds_long_legs[f'{race}_pos'] = leeds_long_legs.index + 1
        leeds_short_legs[f'{race}_pos'] = leeds_short_legs.index + 1
        
        leeds_long_legs = leeds_long_legs[['AthleteId','Name', f'{race}_pos']]
        leeds_short_legs = leeds_short_legs[['AthleteId','Name', f'{race}_pos']]
        
        leeds_short_legs[f"{race}_points"] = leeds_short_legs[f'{race}_pos'].apply(lambda x: 4 + short_weightings[x-1] if x <= len(short_weightings) else 4)
        leeds_long_legs[f"{race}_points"] = leeds_long_legs[f'{race}_pos'].apply(lambda x: 4 + long_weightings[x-1] if x <= len(long_weightings) else 4)
        
        leeds_results = leeds_short_legs.append(leeds_long_legs)
    
    else:
        first = True
        for key, value in race_results.items():
            leg = int(key[-1])
            value['leg'] = leg    
            if first:
                all_results = value
                first = False
            else:
                all_results = all_results.append(value)                                

        leeds_results = all_results[all_results['Club'].str.contains('Leeds City', na=False)].reset_index()
        leeds_results['total_seconds'] = leeds_results[time_index].apply(get_total_seconds)
        leeds_results.loc[leeds_results['leg']==1, ['total_seconds']] += 15
        leeds_results = leeds_results.sort_values(by=['total_seconds']).reset_index()
        leeds_results[f'{race}_pos'] = leeds_results.index + 1

        leeds_results = leeds_results[['AthleteId','Name', f'{race}_pos']]
        leeds_results[f'{race}_points'] = leeds_results[f'{race}_pos'].apply(lambda x: 25 - x if x <= 20 else 4)
        
        
    return leeds_results
        

def get_long_short_legs(race_results, longleg, shortleg):
    
    num_long = 0; num_short = 0
    for key, value in race_results.items():
        if key.startswith(longleg):
            if num_long == 0:
                long_legs = value
            else:
                long_legs = long_legs.append(value)
            num_long += 1
        elif key.startswith(shortleg):
            if num_short == 0:
                short_legs = value
            else:
                short_legs = short_legs.append(value)
            num_short += 1
        else:
            raise ValueError("Found no legs")
    return long_legs, short_legs
    
def get_total_seconds(time_string):
    date_time = datetime.datetime.strptime(time_string, "%M:%S")
    a_timedelta = date_time - datetime.datetime(1900, 1, 1)
    seconds = a_timedelta.total_seconds()
    return seconds


meeting_ids = {
    'national_xc':{
        'id':450428, 'event':'12KXC'
    },
    'northern_xc':{
        'id':445666, 'event':'13.5KXC'
    }
}


race_results_po10 = PowerOf10(load_type='race', base='po10')
race_results_rb = PowerOf10(load_type='race', base='rb')


leeds_nat_xc = get_xc_results(race_results_po10, 'nat_xc', 450428, '12KXC')
leeds_north_xc = get_xc_results(race_results_po10, 'north_xc', 445666, '13.5KXC')

leeds_north_12 = get_relay_results(race_results_rb, 'north_12', 455774, None, multi_distance=True, 
                  leg_weightings=['l','l','l','l','s','s','s','s','s','s','s','s','l','l','s','s','l','l','s','s'],
                  longleg='7.8K', shortleg='3.9K')
leeds_nat_12 = get_relay_results(race_results_rb, 'nat_12', 458578, None, multi_distance=True, 
                    leg_weightings=['l','l','l','l','l','l','s','s','s','s','s','s','l','l','s','s','l','l','s','s'],
                    longleg='8.65K', shortleg='5.08K')

leeds_xc_relay = get_relay_results(race_results_po10, 'nat_xc_relay', 357918, None, multi_distance=False, 
                    leg_weightings=None, time_index='Perf')


leeds_nat_6 = get_relay_results(race_results_rb, 'nat_6', 429886, None, multi_distance=False, 
                    leg_weightings=None, time_index='Gun')

leeds_north_6 = get_relay_results(race_results_rb, 'north_6', 426591, None, multi_distance=False, 
                    leg_weightings=None, time_index='Gun')


all_results = leeds_nat_xc
all_results = all_results.merge(leeds_north_xc, on=['Name'], how='outer')
all_results = all_results.merge(leeds_nat_12, on=['Name'], how='outer')
all_results = all_results.merge(leeds_north_12, on=['Name'], how='outer')
all_results = all_results.merge(leeds_xc_relay, on=['Name'], how='outer')
all_results = all_results.merge(leeds_nat_6, on=['Name'], how='outer')
all_results = all_results.merge(leeds_north_6, on=['Name'], how='outer')

all_results = all_results.fillna(0)

all_results['total_points'] = all_results['nat_xc_points'] + all_results['north_xc_points'] + \
            all_results['north_12_points'] + all_results['nat_12_points'] + all_results['nat_xc_relay_points'] + \
            all_results['north_6_points'] + all_results['nat_6_points']
            
all_results = all_results[['Name','nat_xc_points', 'north_xc_points', 'nat_12_points', 'north_12_points', 'nat_xc_relay_points', 'nat_6_points', 'north_6_points','total_points']]
all_results = all_results.sort_values(by=['Name'], ascending=False).reset_index()
        
print(all_results)


race_results_po10 = PowerOf10(load_type='race', base='po10')
race_results_rb = PowerOf10(load_type='race', base='rb')


leeds_nat_xc = get_xc_results(race_results_po10, 'nat_xc', 316380, '12.9KXC')
leeds_north_xc = get_xc_results(race_results_po10, 'north_xc', 316378, '12.3KXC')

leeds_north_12 = get_relay_results(race_results_rb, 'north_12', 282209, None, multi_distance=True, 
                  leg_weightings=['l','l','l','l','s','s','s','s','s','s','s','s','l','l','s','s','l','l','s','s'],
                  longleg='8K', shortleg='4K')
leeds_nat_12 = get_relay_results(race_results_rb, 'nat_12', 252967, None, multi_distance=True, 
                    leg_weightings=['l','l','l','l','l','l','s','s','s','s','s','s','l','l','s','s','l','l','s','s'],
                    longleg='5.38M', shortleg='3.16M')

leeds_xc_relay = get_relay_results(race_results_po10, 'nat_xc_relay', 316165, None, multi_distance=False, 
                    leg_weightings=None, time_index='Perf')


leeds_nat_6 = get_relay_results(race_results_rb, 'nat_6', 316151, None, multi_distance=False, 
                    leg_weightings=None, time_index='Gun')

leeds_north_6 = get_relay_results(race_results_rb, 'north_6', 316185, None, multi_distance=False, 
                    leg_weightings=None, time_index='Gun')


all_results = leeds_nat_xc
all_results = all_results.merge(leeds_north_xc, on=['Name'], how='outer')
all_results = all_results.merge(leeds_nat_12, on=['Name'], how='outer')
all_results = all_results.merge(leeds_north_12, on=['Name'], how='outer')
all_results = all_results.merge(leeds_xc_relay, on=['Name'], how='outer')
all_results = all_results.merge(leeds_nat_6, on=['Name'], how='outer')
all_results = all_results.merge(leeds_north_6, on=['Name'], how='outer')

all_results = all_results.fillna(0)

all_results['total_points'] = all_results['nat_xc_points'] + all_results['north_xc_points'] + \
            all_results['north_12_points'] + all_results['nat_12_points'] + all_results['nat_xc_relay_points'] + \
            all_results['north_6_points'] + all_results['nat_6_points']
            
all_results = all_results[['Name','nat_xc_points', 'north_xc_points', 'nat_12_points', 'north_12_points', 'nat_xc_relay_points', 'nat_6_points', 'north_6_points','total_points']]
all_results = all_results.sort_values(by=['Name'], ascending=False).reset_index()
        
print(all_results)