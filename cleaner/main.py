import json
import boto3
from botocore.exceptions import ClientError

def get_resources_to_delete(file_path):
    with open(file_path) as f:
        data = json.load(f)
    
    resources = {
        'Route53': [],
        'EC2.Volumes.Attached': [],
        'EC2.Volumes.Created': [],
        'IAM.InstanceProfile': [],
        'IAM.Role': [],
        'S3.Buckets.Created': [],
        'EC2.PlacementGroup': [],
        'EC2.Instances.Created': [],
        'LOGS.LogStream': []
    }

    for record in data['Records']:
        # Handle Route53 record creations
        if record['eventSource'] == 'route53.amazonaws.com' and \
           record['eventName'] == 'ChangeResourceRecordSets' and \
           'requestParameters' in record and \
           record['requestParameters'] is not None and \
           'changeBatch' in record['requestParameters'] and \
           'changes' in record['requestParameters']['changeBatch']:
            changes = record['requestParameters']['changeBatch']['changes']
            for change in changes:
                if change['action'] == 'CREATE':
                    rr_set = change['resourceRecordSet']
                    resources['Route53'].append({
                        'HostedZoneId': record['requestParameters']['hostedZoneId'],
                        'Name': rr_set['name'],
                        'Type': rr_set['type'],
                        'TTL': rr_set.get('tTL', 300),
                        'Values': [rr['value'] for rr in rr_set['resourceRecords']]
                    })
        
        # Handle EC2 volume attachments
        elif record['eventSource'] == 'ec2.amazonaws.com' and \
             record['eventName'] == 'AttachVolume' and \
             'requestParameters' in record and \
             record['requestParameters'] is not None:
            resources['EC2.Volumes.Attached'].append({
                'VolumeId': record['requestParameters']['volumeId'],
                'InstanceId': record['requestParameters']['instanceId'],
                'Device': record['requestParameters']['device']
            })

       # Handle EC2 Volume Creation
        elif record['eventSource'] == 'ec2.amazonaws.com' and \
             record['eventName'] == 'CreateVolume' and \
             'responseElements' in record and \
             record['responseElements'] is not None:
            resources['EC2.Volumes.Created'].append({
                'VolumeId': record['responseElements']['volumeId'],
                'Name': next((item['value'] for item in record['responseElements']['tagSet']['items'] 
                            if item['key'] == 'Name'), 'Unnamed Volume')
            })
        # Handle Bucket Creation
        elif record['eventSource'] == 's3.amazonaws.com' and \
             record['eventName'] == 'CreateBucket' and \
             'requestParameters' in record and \
             record['requestParameters'] is not None:
            resources['S3.Buckets.Created'].append({
                'BucketName': record['requestParameters']['bucketName']
            })
        # Handle Placement Group Creation
        elif record['eventSource'] == 'ec2.amazonaws.com' and \
             record['eventName'] == 'CreatePlacementGroup' and \
             'responseElements' in record and \
             record['responseElements'] is not None:
            resources['EC2.PlacementGroup'].append({
                'PlacementGroupName': record['responseElements']['placementGroup']['groupArn']
            })

        # handle Instance Profile Creation
        elif record['eventSource'] == 'iam.amazonaws.com' and \
             record['eventName'] == 'CreateInstanceProfile' and \
             'responseElements' in record and \
             record['responseElements'] is not None:
            resources['IAM.InstanceProfile'].append({
                'InstanceProfileName': record['responseElements']['instanceProfile']['arn']
            })

        # handle Role Creation
        elif record['eventSource'] == 'iam.amazonaws.com' and \
             record['eventName'] == 'CreateRole' and \
             'responseElements' in record and \
             record['responseElements'] is not None:
            resources['IAM.Role'].append({
                'RoleName': record['responseElements']['role']['arn']
            })

        # Handle Run Instance
        elif record['eventSource'] == 'ec2.amazonaws.com' and \
             record['eventName'] == 'RunInstances' and \
             'responseElements' in record and \
             record['responseElements'] is not None:
            resources['EC2.Instances.Created'].append({
                'InstanceId': record['responseElements']['instancesSet']['items'][0]['instanceId'],
                'Name': next((item['value'] for item in record['responseElements']['instancesSet']['items'][0]['tagSet']['items'] 
                            if item['key'] == 'Name'), 'Unnamed Instance')
            })

        # Handle Log Stream Creation
        elif record['eventSource'] == 'logs.amazonaws.com' and \
             record['eventName'] == 'CreateLogStream' and \
             'responseElements' in record and \
             record['responseElements'] is not None:
            resources['LOGS.LogStream'].append({
                'LogStreamName': record['responseElements']['logStream']['logStreamName']
            })

    return resources

def delete_resources(resources):
    # Initialize clients
    route53 = boto3.client('route53')
    ec2 = boto3.client('ec2')
    iam = boto3.client('iam')
    s3 = boto3.client('s3')

    # Delete Route53 records
    if resources['Route53']:
        print("\nRoute53 Records to delete:")
        for record in resources['Route53']:
            print(f" - {record['Name']} ({record['Type']}): {', '.join(record['Values'])}")
        
        if input("\nDelete these Route53 records? (y/n): ").lower() == 'y':
            for record in resources['Route53']:
                try:
                    route53.change_resource_record_sets(
                        HostedZoneId=record['HostedZoneId'],
                        ChangeBatch={
                            'Changes': [{
                                'Action': 'DELETE',
                                'ResourceRecordSet': {
                                    'Name': record['Name'],
                                    'Type': record['Type'],
                                    'TTL': record['TTL'],
                                    'ResourceRecords': [{'Value': v} for v in record['Values']]
                                }
                            }]
                        }
                    )
                    print(f"Deleted {record['Name']}")
                except ClientError as e:
                    print(f"Error deleting {record['Name']}: {e}")

    #Delete EC2 Instances
    if resources['EC2.Instances.Created']:
        print("\nEC2 Instances to delete:")
        for instance in resources['EC2.Instances.Created']:
            print(f" - Instance {instance['Name']} ({instance['InstanceId']})")
        if input("\nDelete these EC2 instances? (y/n): ").lower() == 'y':
            for instance in resources['EC2.Instances.Created']:
                try:
                    ec2.terminate_instances(InstanceIds=[instance['InstanceId']])
                    print(f"Deleted {instance['InstanceId']}")
                except ClientError as e:
                    print(f"Error deleting {instance['InstanceId']}: {e}")

    # Delete EC2 Volumes
    if resources['EC2.Volumes.Created']:
        print("\nEC2 Volumes to delete:")
        for vol in resources['EC2.Volumes.Created']:
            print(f" - Volume {vol['Name']} ({vol['VolumeId']})")
        if input("\nDelete these EC2 volumes? (y/n): ").lower() == 'y':
            for vol in resources['EC2.Volumes.Created']:
                try:
                    ec2.delete_volume(VolumeId=vol['VolumeId'])
                    print(f"Deleted {vol['VolumeId']}")
                except ClientError as e:
                    print(f"Error deleting {vol['VolumeId']}: {e}")

    # Delete IAM Instance Profiles
    if resources['IAM.InstanceProfile']:
        print("\nIAM Instance Profiles to delete:")
        for profile in resources['IAM.InstanceProfile']:
            print(f" - Instance Profile {profile['InstanceProfileName']}")
        if input("\nDelete these IAM instance profiles? (y/n): ").lower() == 'y':
            for profile in resources['IAM.InstanceProfile']:
                try:
                    iam.delete_instance_profile(arn=profile['InstanceProfileName'])
                    print(f"Deleted {profile['InstanceProfileName']}")
                except ClientError as e:
                    print(f"Error deleting {profile['InstanceProfileName']}: {e}")
    
    # Delete IAM Roles
    if resources['IAM.Role']:
        print("\nIAM Roles to delete:")
        for role in resources['IAM.Role']:
            print(f" - Role {role['RoleName']}")
        if input("\nDelete these IAM roles? (y/n): ").lower() == 'y':
            for role in resources['IAM.Role']:
                try:
                    iam.delete_role(arn=role['RoleName'])
                    print(f"Deleted {role['RoleName']}")
                except ClientError as e:
                    print(f"Error deleting {role['RoleName']}: {e}")
    
    # Delete S3 Buckets
    if resources['S3.Buckets.Created']:
        print("\nS3 Buckets to delete:")
        for bucket in resources['S3.Buckets.Created']:
            print(f" - Bucket {bucket['BucketName']}")
        if input("\nDelete these S3 buckets? (y/n): ").lower() == 'y':
            for bucket in resources['S3.Buckets.Created']:
                try:
                    s3.delete_bucket(Bucket=bucket['BucketName'])
                    print(f"Deleted {bucket['BucketName']}")
                except ClientError as e:
                    print(f"Error deleting {bucket['BucketName']}: {e}")

    # # Detach EC2 volumes
    # if resources['EC2.Volumes.Attached']:
    #     print("\nEC2 Volumes to detach:")
        
    #     for vol in resources['EC2.Volumes.Attached']:
    #         print(f" - Volume {vol['VolumeId']} from instance {vol['InstanceId']}")
        
    #     if input("\nDetach these EC2 volumes? (y/n): ").lower() == 'y':
    #         for vol in resources['EC2.Volumes.Attached']:
    #             if input(f"Detach {vol['VolumeId']} from {vol['InstanceId']}? (y/n): ").lower() == 'y':
    #                 try:
    #                     ec2.detach_volume(
    #                         VolumeId=vol['VolumeId'],
    #                         InstanceId=vol['InstanceId'],
    #                         Device=vol['Device']
    #                     )
    #                     print(f"Detached {vol['VolumeId']} from {vol['InstanceId']}")
    #                 except ClientError as e:
    #                     print(f"Error detaching {vol['VolumeId']}: {e}")


if __name__ == '__main__':
    #file_path = input("Enter path to AWS resources JSON file: ")
    file_path = './aws-resources.json'
    resources = get_resources_to_delete(file_path)
    
    if not any(resources.values()):
        print("No deletable resources found in the file")
        exit()

    print(f"\nFound:  \n{len(resources['Route53'])} Route53 records \n{len(resources['EC2.Volumes.Attached'])} EC2 volumes Attached \n{len(resources['EC2.Volumes.Created'])} EC2 volumes Created \n{len(resources['IAM.InstanceProfile'])} IAM instance profiles \n{len(resources['IAM.Role'])} IAM roles \n{len(resources['S3.Buckets.Created'])} S3 buckets \n{len(resources['EC2.PlacementGroup'])} EC2 placement groups \n{len(resources['EC2.Instances.Created'])} EC2 instances")
    print(f"\nTotal resources to delete: {sum(len(v) for v in resources.values())}")
    if input("Show resources to be deleted? (y/n): ").lower() == 'y':
        delete_resources(resources)
    else:
        print("Aborted")