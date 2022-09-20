import pandas as pd
import requests
import re
import numpy as np
from bs4 import BeautifulSoup
from datetime import timedelta as dt

import settings 

class PowerOf10():

    def __init__(self,load_type='athlete', base='po10'):
        """Initiate a po10 object for athlete, race or rankings

        Args:
            load_type (str, optional): Type of data to load - athlete, race or rankings. Defaults to 'athlete'.
        """
        if load_type not in settings.DATA_LOAD_TYPES:
            raise ValueError(f'Load type must be one of {settings.DATA_LOAD_TYPES}.')
        self.type=load_type
        
        if base == 'po10':
            self.root_url = settings.PO10_ROOT_URL
            self.table_id = settings.PO10_TABLE_ID
        elif base == 'rb':
            self.root_url = settings.RUNBRITAIN_ROOT_URL
            self.table_id = settings.RB_TABLE_ID
    
    def getData(self,url):
        """Scrape the power of 10 page for the data.

        Args:
            url (_type_): URL of po10 page to load from. 

        Returns:
            _type_: BeatifulSoup page
        """
        ''' Initial load of data'''
        data_content = requests.get(url).content
        data = BeautifulSoup(data_content,'html.parser')
        return data
    
    def athleteDetails(self, url):
        """Get the details of a particular athlete.

        Args:
            url (str): URL of athlete's po10 profile.

        Returns:
            list (dict, dict, dict, dict): List of dictionaries of athlete's detials
        """
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
        soup = self.getData(self.root_url + \
            f'/rankings/rankinglist.aspx?event={event}&agegroup={age_group}&sex={sex}&year={year}')
        
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
    
    
    def get_results(self, meeting_id, event=None):
        """
        Get results from a meeting
        
        # Parameters
        meeting_id : string or int
        
        # Returns
        results : dict of DataFrames, results by event.
        """
        if event is not None:
            url_string = f'/results/results.aspx?meetingid={meeting_id}&event={event}'
        else:
            url_string = f'/results/results.aspx?meetingid={meeting_id}'
        soup = self.getData(self.root_url + url_string)
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
                soup = self.getData(self.root_url + url_string + \
                    f'&pagenum={i}')
            results_soup = soup.find('table', {'id': self.table_id})
            df = pd.read_html(str(results_soup), header=None)[0]
            # Attach athlete ids
            athlete_ids = []
            for row in results_soup.find_all('tr'):
                
                th = row.find_all('th')
                if len(th) > 0:
                    continue
                    
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
            ix = np.where(df.iloc[:,3]==df.iloc[:,6])[0]
            if len(ix) > 1:
                dfs = [df[ix[j]:ix[j+1]] for j in range(len(ix)-1)]
                dfs = dfs + [df[ix[-1]:]]
            else:
                dfs = [df[ix[0]:]]
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
        page = self.getData(self.root_url + \
            f'/athletes/athleteslookup.aspx?surname={surname}&firstname={first_name}&club={club}')
        
        search = page.find('table', {'id': 'cphBody_dgAthletes'})
        df = pd.read_html(str(search), header=0)[0]
        df = df.drop(['runbritain', 'Profile'], axis=1)
        df.index = [int(re.findall(r'\d+', x.get('href'))[0]) for x in search.find_all('a', {'href': re.compile('^((?!run).)*$')})]
        return df
    