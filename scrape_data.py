import pandas as pd
import requests
import os
import time
import re
import numpy as np
from bs4 import BeautifulSoup
from datetime import timedelta as dt

root_url = 'http://www.thepowerof10.info/'

class PowerOf10():
    def __init__(self,load_type='athlete'):
        '''
        Load data for athelte, race, rankings
        '''
        self.type=load_type
    
    def getData(self,url):
        ''' Initial load of data'''
        data_content = requests.get(url).content
        data = BeautifulSoup(data_content,'html.parser')
        return data
    
    def athleteDetails(self,url):
        data = self.getData(url)
        name = data.find('h2').text.strip()
        athDet_soup = data.find('div',{'id':'cphBody_pnlAthleteDetails'})
        athDet_df = pd.concat(pd.read_html(str(athDet_soup))[1:],ignore_index=True)
        athDets = dict(zip([x.strip(':') for x in athDet_df[0]], athDet_df[1]))
        athDets['Club']  = athDets['Club'].split('/')
        athDets['Name'] = name
        
        SBs_soup = data.find('div',{'id':'cphBody_divBestPerformances'})
        SBs_df = pd.read_html(str(SBs_soup),header=0)[0]
        SBs_df.Event = SBs_df.Event.astype(str)
        SBs_df = SBs_df[SBs_df.Event != 'Event']
        SBs_df.index = SBs_df.Event
        SBs_df = SBs_df.drop(SBs_df.columns[['Event' in x for x in SBs_df.columns]],axis=1)
        SBs_df = SBs_df[~SBs_df.index.duplicated(keep='first')]
        
        res_soup = data.find('div',{'id':'cphBody_pnlPerformances'})
        res_soup_tab = res_soup.find_all('table')[1]
        res_df = pd.read_html(str(res_soup_tab))[0]
        res_df.columns = ['Event', 'Perf', 'Notes', 'Wind', 'Chip', 'Pos', 'Race',
                          'Unknown', 'CatPos', 'Venue', 'Meeting', 'Date']
        
        yearly_info = res_df[res_df.Date==res_df.Event].Event
        years = [int(x.split()[0]) for x in yearly_info]
        ags = [x.split()[1] for x in yearly_info]
        clubs = [' '.join(x.split()[2:]).split('/') for x in yearly_info]
        yearly_info = dict(zip(years, [{'age_group': a, 'clubs': c} for a,c in zip(ags, clubs)]))
        
        
        # Get meeting ids
        meeting_ids = []
        for row in res_soup_tab.find_all('tr'):
            a = row.find('a')
            if a is None:
                meeting_ids.append(-1)
                continue
            url = a.get('href', '')
            match = re.findall(r'meetingid=\d+', url)
            
            if len(match) == 0:
                meeting_ids.append(-1)
            else:
                meeting_ids.append(int(match[0][10:]))
                
        res_df['MeetingId'] = meeting_ids
        
        
        res_df = res_df[np.logical_not(np.logical_or(res_df.Date==res_df.Event, res_df.Date == 'Date'))]
        return athDets, yearly_info, SBs_df, res_df
    
    def get_rankings(self, event, age_group, sex, year):
        """
        Get rankings
        
        # Parameters
        event     : string
        age_group : string
        sex       : string
        year      : string or int
        
        # Returns
        rankings : DataFrame, rankings indexed by athlete id.
        """
        soup = self.getData(root_url + '/rankings/rankinglist.aspx?event={}&agegroup={}&sex={}&year={}'.format(event, age_group, sex, year))
        
        rankings = soup.find('span', {'id': 'cphBody_lblCachedRankingList'})
        df = pd.read_html(str(rankings))[0] 
        
        # Header row has first column 'Rank'
        header_row = df.index[df[0] == 'Rank'][0]
        df.columns = ['Rank', 'Perf', 'Notes', 'Wind', 'PB', 'IsPB',  'Name', 'AgeGroup',
            'Year', 'Coach',  'Club', 'Venue',  'Date', 'Notify']
        df = df.iloc[header_row+1:]
        df = df[~df.Perf.isnull()] # Drop rows without a performance
        df = df[~df.Rank.isnull()] # Drop non-UK table (unranked)
        df = df.drop(df[df.Rank==df.Notify].index)
        df = df.drop('Notify', axis=1) # Drop last column
        df.Rank = df.Rank.astype(int) 
    
        # Find athlete_ids
        rows = [x.find('a') for x in rankings.find_all('tr')]
        links = [x.get('href') for x in rows if x is not None]
        athlete_ids = [int(re.findall(r'\d+', x)[0]) for x in links if 'athleteid=' in x]
        athlete_ids = athlete_ids[:len(df)]
        df.index = athlete_ids
        return df
    
    
    def get_results(self, meeting_id):
        """
        Get results from a meeting
        
        # Parameters
        meeting_id : string or int
        
        # Returns
        results : dict of DataFrames, results by event.
        """
        soup = self.getData(root_url + '/results/results.aspx?meetingid={}&top=5000&pagenum=1'.format(meeting_id))
        # Get the number of pages
        num_pages = 1
        num_pages_soup = soup.find('span', {'id': 'cphBody_lblTopPageLinks'})
        if num_pages_soup is not None:
            links = num_pages_soup.find_all('a')
            if len(links) > 0:
                num_pages = max([int(a.text) for a in links])
        results = {}
        for i in range(1, num_pages+1):
            # Load the next page if appropriate.
            if i > 1:
                soup = self.getData(root_url + '/results/results.aspx?meetingid={}&top=5000&pagenum={}'.format(meeting_id, i))
                
            results_soup = soup.find('table', {'id': 'cphBody_dgP'})
            df = pd.read_html(str(results_soup), header=None)[0]
            # Attach athlete ids
            athlete_ids = []
            for row in results_soup.find_all('tr'):
                a = row.find('a')
                if a is None:
                    athlete_ids.append(-1)
                    continue
                url = a.get('href', '')
                match = re.findall(r'athleteid=\d+', url)
                
                if len(match) == 0:
                    athlete_ids.append(-1)
                else:
                    athlete_ids.append(int(match[0][10:]))
            df['AthleteId'] = athlete_ids
            # Drop rows which are blank (excl. athlete_id)
            df = df[~((~df.isnull()).sum(axis=1) == 1)]
            # Those with rows with only one entry (excl. athlete_id) are the 
            # header rows containing the age group and distance.
            ix = np.where(df[3]==df[6])[0]
            
            dfs = [df[ix[j]:ix[j+1]] for j in range(len(ix)-1)]

            for df in dfs:
                race = df.iloc[0,0]
                df.columns = list(df.iloc[1, :-1]) + ['AthleteId'] # Often a variable number of columns so don't set manually
                df = df.iloc[2:]
                
                if race in results:
                    results[race] = pd.concat((results[race], df))
                else:
                    results[race] = df
                
            for name, df in results.items():
                results[name] = df.reset_index(drop=True)
            
        return results
    
    def search(self,first_name='',surname='',club=''):
        """
            Search for athletes with the given name and club.
            
            # Parameters
            first_name : string
            surname    : string
            club       : string
            
            # Returns
            search_results : DataFrame, search results indexed by athlete id.
        """
        page = self.getData(root_url + '/athletes/athleteslookup.aspx?surname={}&firstname={}&club={}'
                       .format(surname, first_name , club))
        
        search = page.find('table', {'id': 'cphBody_dgAthletes'})
        df = pd.read_html(str(search), header=0)[0]
        df = df.drop(['runbritain', 'Profile'], axis=1)
        df.index = [int(re.findall(r'\d+', x.get('href'))[0]) for x in search.find_all('a', {'href': re.compile('^((?!run).)*$')})]
        return df
    

def main():
    po10 = PowerOf10()
    #team2008 = []
    #team2013 = []
    team2014 = [['Simon','Deakin','Leeds','l'],
                ['Jonathan','Wills','Roundhay','s'],
                ['James','Walsh','Leeds','l'],
                ['Gordon','Benson','Leeds','s'],
                ['Stephen','Lisgo','Leeds','l'],
                ['Dominic','Easter','Leeds','s'],
                ['James','Wilkinson','Leeds','l'],
                ['Dan','Davis','Aldershot','s'],
                ['Carl','Smith','Birmingham','l'],
                ['Thomas','Edwards','Leeds','s'],
                ['Luke','Cragg','Leeds','l'],
                ['Nick','Hooker','Leeds','s']
                ]

    team2019 = [['Wondiye','Indelbu','Leeds','l'],
                ['Josh','Woodcock','Leeds','s'],
                ['John','Ashcroft','Leeds','l'],
                ['Matthew','Grieve','Leeds','s'],
                ['Oliver','Lockley','Leeds','l'],
                ['Michael','Salter','Leeds','s'],
                ['Phil','Sesemann','Leeds','l'],
                ['Ossama','Meslek','Leeds','s'],
                ['Linton','Taylor','Leeds','l'],
                ['Emile','Cairess','Leeds','s'],
                ['Graham','Rush','Leeds','l'],
                ['Joe','Townsend','Leeds','s']]
    
    
    sbs2014 = []; sbs2019 = []; pbs2019 = []; pbs2014 = []
    for leg_2014, leg_2019 in zip(team2014, team2019):
        print(leg_2014)
        ath_2014 = po10.search(first_name=leg_2014[0],surname=leg_2014[1],club=leg_2014[2]).index[0]
        ath_2019 = po10.search(first_name=leg_2019[0],surname=leg_2019[1],club=leg_2019[2]).index[0]       
        url2014 = root_url + 'athletes/profile.aspx?athleteid={0}'.format(ath_2014)
        url2019 = root_url + 'athletes/profile.aspx?athleteid={0}'.format(ath_2019)
        ath2014a = po10.athleteDetails(url2014)[2]
        ath2019a = po10.athleteDetails(url2019)[2]
        if leg_2014[3] == 'l':
            event = '10K'
            event2 = '10000'
        else:
            event = '5K'
            event2 = '5000'
        if not event in ath2014a.index:
            sbs2014.append(np.nan)
        else:
            ath2014 = ath2014a.loc[event]
            sb2014 = ath2014['2014']
            if not isinstance(sb2014,str):
                if event2 in ath2014a.index and isinstance(ath2014a.loc[event2]['2014'],str):
                    sb2014 = ath2014a.loc[event2]['2014']
                    
                elif isinstance(ath2014['2015'],str):
                    sb2014 = ath2014['2015']
                elif isinstance(ath2014['2013'],str):
                    sb2014 = ath2014['2013']
                else:
                    sb2014 = ath2014['PB']
            pbs2014.append(ath2014['PB'])
            sbs2014.append(sb2014)

        if not event in ath2019a.index:
            sbs2019.append('15:48') # JWS
            pbs2019.append('15:26')
        else:
            ath2019 = ath2019a.loc[event]
            sb2019 = ath2019['2019']
            if not isinstance(sb2019,str):
                if event2 in ath2019a.index and isinstance(ath2019a.loc[event2]['2019'],str):
                    sb2019 = ath2019a.loc[event2]['2019']
                elif isinstance(ath2019['2020'],str):
                    sb2019 = ath2019['2020']
                elif isinstance(ath2019['2018'],str):
                    sb2019 = ath2019['2018']
                else:
                    sb2019 = ath2019['PB']

            pb2019 = ath2019['PB']
            sbs2019.append(sb2019)
            pbs2019.append(pb2019)
        
                
        
        
#        ath2019 = ath2019.loc[event]    
#        
#        if event not in ath2019:
#            ath2019[event] = 'NAN'
#        
#        
#        
#        sb2019 = ath2019['2019']
#        sbs2019.append(sb2019)
        
    print(sbs2014)
    print(sbs2019)
    print(pbs2014)
    print(pbs2019)
    sbelapsed2014 = dt(minutes=0,seconds=0); sbtottime2014 = []
    sbelapsed2019 = dt(minutes=0,seconds=0); sbtottime2019 = []
    print(sbelapsed2014)
    for sbleg2014, sbleg2019 in zip(sbs2014, sbs2019):
        legtime2014 = dt(minutes=int(sbleg2014[0:2]),seconds=int(sbleg2014[3:5]))
        sbelapsed2014 = sbelapsed2014 + legtime2014
        legtime2019 = dt(minutes=int(sbleg2019[0:2]),seconds=int(sbleg2019[3:5]))
        sbelapsed2019 = sbelapsed2019 + legtime2019
        sbtottime2014.append(str(sbelapsed2014))
        sbtottime2019.append(str(sbelapsed2019))
    
    pbelapsed2014 = dt(minutes=0,seconds=0); pbtottime2014 = []
    pbelapsed2019 = dt(minutes=0,seconds=0); pbtottime2019 = []
    
    for pbleg2014, pbleg2019 in zip(pbs2014, pbs2019):
        legtime2014 = dt(minutes=int(pbleg2014[0:2]),seconds=int(pbleg2014[3:5]))
        pbelapsed2014 = pbelapsed2014 + legtime2014
        legtime2019 = dt(minutes=int(pbleg2019[0:2]),seconds=int(pbleg2019[3:5]))
        pbelapsed2019 = pbelapsed2019 + legtime2019
        pbtottime2014.append(str(pbelapsed2014))
        pbtottime2019.append(str(pbelapsed2019))
        
    print(sbtottime2014)
    print(sbtottime2019)
    print(pbtottime2014)
    print(pbtottime2019)
    
#        sb_ath2014 = 


    #zara1, zara2, zara3, zara4 = po10.athleteDetails('https://thepowerof10.info/athletes/profile.aspx?athleteid=909')
    #print(zara1)
    #rankings = po10.get_rankings('1500','ALL','M',2010)
#    print(results)
    
    

    
if __name__=='__main__':
    main()
