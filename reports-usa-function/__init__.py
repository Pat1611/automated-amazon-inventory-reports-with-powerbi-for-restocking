import logging
import time
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import os
import azure.functions as func
import requests
from datetime import datetime, timedelta, timezone
import tempfile

refresh_token = os.environ["REFRESH_TOKEN_USA"]
client_id= os.environ["CLIENT_ID"]
client_secret = os.environ["CLIENT_SECRET"]
storage_account_connection_string = os.environ["STORAGE_ACCOUNT_CONNECTION_STRING"]


def main(mytimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()  # Use timezone.utc

    if mytimer.past_due:
        logging.info('The timer is past due!')

    logging.info('Python timer trigger function ran at %s', utc_timestamp)

    call_amazon_authentication()
    
# POST access_ token for reports
def call_amazon_authentication():
    url = "https://api.amazon.com/auth/o2/token"
    params = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
        
    }

    response = requests.post(url,params=params)
    if response.status_code==200:
        logging.info("HTTP request successful.")
        data=response.json()
        access_token=data.get("access_token")
        if access_token:
            logging.info("Access token: %s", access_token)
            report_type = "GET_RESTOCK_INVENTORY_RECOMMENDATIONS_REPORT" #30days USA
            marketplace_ids = ["ATVPDKIKX0DER"]
            report_name= "30days_USA.txt"
        
            call_amazon_raports(access_token,report_type,marketplace_ids,report_name)
            
            report_type = "GET_FBA_INVENTORY_PLANNING_DATA" #90 days USA
            marketplace_ids = ["ATVPDKIKX0DER"]
            report_name= "90days_USA.txt"
            
            call_amazon_raports(access_token,report_type,marketplace_ids,report_name)
            
            
        else:
            logging.error("No access token found in the response.")
    else:
        logging.error("HTTP request failed. Status code: %s", response.status_code)
        
def call_amazon_raports(access_token,report_type, marketplace_ids, report_name):
    url ="https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports"  
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-amz-access-token": f"{access_token}"
    }
    data_end_time = datetime.utcnow()  # Today's date in UTC
    data_start_time = data_end_time - timedelta(days=30)  # 30 days before today

    body = {
        "marketplaceIds":marketplace_ids,
        "reportType": report_type,
        "dataStartTime": data_start_time.isoformat() + "Z",
        "dataEndTime": data_end_time.isoformat() + "Z"
    }
    response = requests.post(url, json=body, headers=headers)  # Making the GET request with headers
    if response.status_code == 202:
        logging.info("Authenticated HTTP request successful.")
        data=response.json()
        reportId=data.get("reportId")
        logging.info("Response: %s", response.text)
        time.sleep(35)
        call_amazon_specific_report(reportId,access_token,report_name)
    else:
        logging.error("Authenticated HTTP request failed. Status code: %s", response.status_code)
        
     
      # GET - generate raport 30 days inventory
      
def call_amazon_specific_report(reportId, access_token,report_name):
    url = f"https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports/{reportId}"  # Embed reportId into the URL
    headers = {
        "Accept": "application/json",
        "x-amz-access-token": f"{access_token}"
    }
    response = requests.get(url, headers=headers)  # Making the GET request with headers
    if response.status_code == 200:
        logging.info("Authenticated HTTP request successful.")
        data=response.json()
        reportDocumentId=data.get("reportDocumentId")
        logging.info("Response: %s", response.text)
        call_amazon_document(reportDocumentId,access_token,report_name)
    else:
        logging.error("Authenticated HTTP request failed. Status code: %s", response.status_code)
    
def call_amazon_document(reportDocumentId, access_token,report_name):
    url = f"https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/documents/{reportDocumentId}"  # Embed reportId into the URL
    headers = {
        "Accept": "application/json",
        "x-amz-access-token": f"{access_token}"
    }
    response = requests.get(url, headers=headers)  # Making the GET request with headers
    if response.status_code == 200:
        logging.info("Authenticated HTTP request successful.")
        data=response.json()
        url=data.get("url")
        logging.info("Response: %s", response.text)
        connection_string = storage_account_connection_string
        container_name_30 = '30days-reports'
        container_name_90 = '90days-reports'
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)

        call_amazon_download(url,container_name_30,container_name_90,blob_service_client,report_name)
        
    else:
        logging.error("Authenticated HTTP request failed. Status code: %s", response.status_code)      

def call_amazon_download(url,container_name_30,container_name_90,blob_service_client,report_name):
    # Step 1: Download the content
    response = requests.get(url)
    if response.status_code == 200:
        content = response.text

        # Step 2: Save as .txt file
        temp_dir = tempfile.gettempdir()
        file_name = report_name
        temp_file_path = os.path.join(temp_dir, file_name)
        with open(temp_file_path, 'w') as file:
            file.write(content)
            
        # Step 3: Determine the correct container based on report_name
        if report_name.startswith('30days'):
            container_name = container_name_30
        elif report_name.startswith('90days'):
            container_name = container_name_90
        else:
            logging.error(f"Invalid report name: {report_name}")
            return

        # Step 4: Upload to Azure Blob Storage
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=file_name)
        with open(temp_file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)

        os.remove(temp_file_path) 
        logging.info(f"File uploaded to Azure Blob Storage: {container_name}/{file_name}")
    else:
        logging.error(f"Failed to download content from URL: {url}")
        
        