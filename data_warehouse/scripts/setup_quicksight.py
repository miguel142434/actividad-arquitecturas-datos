#!/usr/bin/env python3
"""Alta explícita de QuickSight y activos; ejecutar solo tras aprobar costos/IAM."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import boto3
from botocore.exceptions import ClientError
from ecommerce_dw.consumption.assets import requests, DATASET_ID


def wait_for(read, key, good, bad, attempts=120):
    for _ in range(attempts):
        value = read()
        status = value[key]
        if status in good:
            return value
        if status in bad:
            raise RuntimeError('El recurso QuickSight quedó en estado fallido: '+status)
        time.sleep(5)
    raise TimeoutError('QuickSight no terminó dentro del tiempo de revisión.')


def ensure(client, create, update, payload):
    try:
        return getattr(client, create)(**payload)
    except ClientError as error:
        if error.response['Error']['Code'] != 'ResourceExistsException':
            raise
        operation = client.meta.method_to_api_mapping[update]
        allowed = client.meta.service_model.operation_model(operation).input_shape.members
        return getattr(client, update)(**{k:v for k,v in payload.items() if k in allowed})


def reader_credentials(target):
    # La contraseña viaja solo por SSH/stdin/stdout capturados en memoria; nunca
    # en argumentos, historial, archivos, evidencia ni estado Terraform.
    program = '''
import json,secrets
from contextlib import closing
from ecommerce_dw.warehouse.connection import connect_redshift
name='de_dw_aws_qs_reader'
password='Aa9'+secrets.token_urlsafe(30)
with closing(connect_redshift()) as connection:
 with connection.cursor() as cursor:
  cursor.execute('SELECT usesuper FROM pg_user WHERE usename=%s',(name,))
  row=cursor.fetchone()
  if row and row[0]:raise RuntimeError('No reutilizar un superusuario como lector de QuickSight')
  statement='ALTER USER de_dw_aws_qs_reader PASSWORD %s' if row else 'CREATE USER de_dw_aws_qs_reader PASSWORD %s NOCREATEDB NOCREATEUSER'
  cursor.execute(statement,(password,))
  cursor.execute('GRANT USAGE ON SCHEMA marts TO de_dw_aws_qs_reader')
  cursor.execute('GRANT SELECT ON marts.fct_sales,marts.dim_date,marts.dim_product,marts.dim_sales_channel TO de_dw_aws_qs_reader')
 connection.commit()
print('CREDENTIAL_PAIR='+json.dumps({'Username':name,'Password':password}))
'''
    command = ['ssh','-i',str(Path('~/.ssh/id_ed25519').expanduser()),'-o','BatchMode=yes',
               '-o','StrictHostKeyChecking=yes',target,
               'cd /opt/de-dw-aws && docker compose --project-directory . --env-file .env '
               '-f docker/docker-compose.yml exec -T airflow-scheduler /home/airflow/dbt-venv/bin/python -']
    result = subprocess.run(command,input=program,text=True,capture_output=True)
    if result.returncode:
        raise RuntimeError('No se pudo preparar el lector SQL; no se muestra la salida para proteger el secreto.')
    return json.loads(next(line[len('CREDENTIAL_PAIR='):] for line in result.stdout.splitlines()
                           if line.startswith('CREDENTIAL_PAIR=')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-id',required=True)
    parser.add_argument('--notification-email',required=True)
    parser.add_argument('--owner-iam-arn',required=True)
    parser.add_argument('--ssh-target',required=True)
    parser.add_argument('--redshift-host',required=True)
    parser.add_argument('--vpc-arn',required=True)
    parser.add_argument('--activate-account',action='store_true',help='Solicita suscripción Enterprise y termina; solo con autorización previa')
    args = parser.parse_args()
    session=boto3.Session(profile_name='default',region_name='us-east-1')
    if session.client('sts').get_caller_identity()['Account'] != args.account_id:
        raise ValueError('La identidad no coincide con la cuenta esperada.')
    client=session.client('quicksight',region_name='us-east-1')
    try:
        subscription=client.describe_account_subscription(AwsAccountId=args.account_id)['AccountInfo']
    except ClientError as error:
        if error.response['Error']['Code']!='ResourceNotFoundException' or not args.activate_account:
            raise
        client.create_account_subscription(AwsAccountId=args.account_id,AccountName='de-dw-aws-'+args.account_id,
            Edition='ENTERPRISE',AuthenticationMethod='IAM_AND_QUICKSIGHT',NotificationEmail=args.notification_email)
        subscription=None
    if subscription and subscription['Edition']!='ENTERPRISE':
        raise ValueError('Se requiere Enterprise sin Pro/Q; no cambiar edición automáticamente.')
    if args.activate_account:
        print(json.dumps({'account_id':args.account_id,'edition':'ENTERPRISE','subscription_requested':True}))
        return
    # No alterar la conexión ni IAM: Terraform debe haberla creado con aprobación.
    wait_for(lambda:client.describe_vpc_connection(AwsAccountId=args.account_id,
        VPCConnectionId='de-dw-aws-warehouse')['VPCConnection'],'AvailabilityStatus',{'AVAILABLE'},{'UNAVAILABLE'})
    username=args.owner_iam_arn.rsplit('/',1)[-1]
    users=client.list_users(AwsAccountId=args.account_id,Namespace='default')['UserList']
    matches=[u for u in users if u['UserName']==username]
    if matches:
        principal=matches[0]['Arn']
    elif len(users)==1 and users[0]['Role'] in {'ADMIN','ADMIN_PRO'}:
        # Reutilizar el administrador creado en consola; no añadir otro asiento.
        principal=users[0]['Arn']
    else:
        raise ValueError('No se identificó un administrador único; revisar usuarios antes de añadir asientos.')
    payloads=requests(args.account_id,principal,args.redshift_host,args.vpc_arn)
    payloads['source']['Credentials']={'CredentialPair':reader_credentials(args.ssh_target)}
    ensure(client,'create_data_source','update_data_source',payloads['source'])
    del payloads['source']['Credentials']
    wait_for(lambda:client.describe_data_source(AwsAccountId=args.account_id,
        DataSourceId='de-dw-aws-redshift')['DataSource'],'Status',{'CREATION_SUCCESSFUL','UPDATE_SUCCESSFUL'},
        {'CREATION_FAILED','UPDATE_FAILED','DELETED'})
    response=ensure(client,'create_data_set','update_data_set',payloads['dataset'])
    ingestion_id=response.get('IngestionId')
    if ingestion_id:
        wait_for(lambda:client.describe_ingestion(AwsAccountId=args.account_id,DataSetId=DATASET_ID,
            IngestionId=ingestion_id)['Ingestion'],'IngestionStatus',{'COMPLETED'},{'FAILED','CANCELLED'})
    ensure(client,'create_analysis','update_analysis',payloads['analysis'])
    wait_for(lambda:client.describe_analysis(AwsAccountId=args.account_id,
        AnalysisId='de-dw-aws-sales')['Analysis'],'Status',{'CREATION_SUCCESSFUL','UPDATE_SUCCESSFUL'},
        {'CREATION_FAILED','UPDATE_FAILED','DELETED'})
    response=ensure(client,'create_dashboard','update_dashboard',payloads['dashboard'])
    version=int(response['VersionArn'].rsplit('/',1)[-1])
    dashboard=wait_for(lambda:client.describe_dashboard(AwsAccountId=args.account_id,
        DashboardId='de-dw-aws-sales',VersionNumber=version)['Dashboard']['Version'],'Status',{'CREATION_SUCCESSFUL','UPDATE_SUCCESSFUL'},
        {'CREATION_FAILED','UPDATE_FAILED','DELETED'})
    client.update_dashboard_published_version(AwsAccountId=args.account_id,DashboardId='de-dw-aws-sales',
                                             VersionNumber=dashboard['VersionNumber'])
    print(json.dumps({'principal_arn':principal,'dataset_id':DATASET_ID,'dashboard_id':'de-dw-aws-sales',
        'url':'https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/de-dw-aws-sales'},ensure_ascii=False))


if __name__=='__main__':
    try:
        main()
    except ClientError as error:
        raise SystemExit('QuickSight: '+error.operation_name+' '+error.response['Error']['Code']) from None
    except Exception as error:
        raise SystemExit('Configuración incompleta: '+type(error).__name__+'; conservar recursos y revisar el paso sin mostrar secretos.') from None
