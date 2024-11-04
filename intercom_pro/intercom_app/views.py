import threading
import time
import queue
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view
import asterisk.manager


def one_to_one_call1(ami_host, ami_port, ami_user, ami_password, from_extn, to_extn):
    try:
        # Connect to the Asterisk AMI
        ami = asterisk.manager.Manager()
        ami.connect(ami_host, ami_port)
        ami.login(ami_user, ami_password)

        channel_id = None

        # Define a callback function to capture events
        def on_event(event, manager):
            print("inside")
            print(event)
            print(type(event))
            print(dir(event))
            print(event.data)
            print(event.name)
            print(event.get_header)
            print(event.headers)
            print(event.message)
            print("inside1")
            nonlocal channel_id
            # Check if the event is the one indicating that the call is answered
            if event.name == "OriginateResponse" and event.get("Response") == "Success":
                # Capture the channel ID
                channel_id = event.get("Channel")
                # Disconnect from the AMI after capturing the channel
                manager.close()

        # Register the event listener
        ami.register_event('OriginateResponse', on_event)

        # Originate action details
        action = {
            'channel': f'PJSIP/{from_extn}',
            'context': 'from-internal',
            'exten': f'{to_extn}',
            'priority': 1,
            'caller_id': f'SoftPhone <{from_extn}>',
            'timeout': 30000,
            'run_async': True,
            'variables': {
                'PJSIP_HEADER(add,Alert-Info)': 'info=AutoAnswer'
            }
        }
        # Send the originate action
        # response = ami.originate(**action)
        # ami.logoff()
        # if response and hasattr(response, 'get_header'):
        #     channel_id = response.get_header('Uniqueid')  # Adjust if you get a different attribute
        # else:
        #     channel_id = None

        # Convert the response to a JSON-serializable format
        # print(dir(response))
        # response_dict = {
        #     'response': str(response.response),
        #     'channel_id': channel_id
        # }
        # Send the originate action
        ami.originate(**action)

        # Wait for the event callback to get triggered
        # ami.loop(timeout=30)  # Listen for events for up to 30 seconds

        ami.logoff()

        # Return the captured channel ID
        return {'channel_id': channel_id} if channel_id else {'error': 'No channel captured'}
        # return response_dict
    except Exception as e:
        return {'error': str(e)}


def one_to_one_call(ami_host, ami_port, ami_user, ami_password, from_extn, to_extn):
    try:
        # Connect to the Asterisk AMI
        ami = asterisk.manager.Manager()
        ami.connect(ami_host, ami_port)
        ami.login(ami_user, ami_password)

        channel_id = None
        response_received = threading.Event()  # Create an event for synchronization

        # Define a callback function to capture events
        def on_event(event, manager=None):
            nonlocal channel_id
            print(f"Received event: {event}")  # Log the received event

            # Accessing headers to get the required information
            if event.name == "OriginateResponse":
                response = event.headers.get("Response")
                if response == "Success":
                    channel_id = event.headers.get("Channel")  # Extract channel ID
                    response_received.set()  # Signal that the response has been received
                else:
                    print(f"OriginateResponse: {response}")

        # Register the event listener
        ami.register_event('OriginateResponse', on_event)

        # Originate action details
        action = {
            'Action': 'Originate',
            'Channel': f'PJSIP/{from_extn}',
            'Context': 'from-internal',
            'Exten': f'{to_extn}',
            'Priority': 1,
            'CallerID': f'SoftPhone <{from_extn}>',
            'Timeout': 30000,
            'Async': True,
            'Variable': 'PJSIP_HEADER(add,Alert-Info)=info=AutoAnswer'
        }

        # Send the originate action
        ami.send_action(action)

        # Use a separate thread to retrieve events from the event queue
        def event_listener():
            while not response_received.is_set():
                try:
                    event = ami._event_queue.get(timeout=1)  # Get the next event, wait for up to 1 second
                    on_event(event)  # Process the event
                except queue.Empty:
                    continue  # Continue if the queue is empty

        event_thread = threading.Thread(target=event_listener)
        event_thread.start()

        # Wait for the event to be set (response received) or timeout
        response_received.wait(timeout=30)  # Wait for up to 30 seconds

        ami.logoff()

        # Check if channel_id was captured
        return {'channel_id': channel_id} if channel_id else {'error': 'No channel captured'}

    except Exception as e:
        return {'error': str(e)}


def hangup_call(ami_host, ami_port, ami_user, ami_password, channel_id):
    try:
        # Connect to the Asterisk AMI
        ami = asterisk.manager.Manager()
        ami.connect(ami_host, ami_port)
        ami.login(ami_user, ami_password)

        # Send the hangup action
        action = {
            'Action': 'Hangup',
            'Channel': channel_id
        }

        response = ami.send_action(action)

        ami.logoff()

        # Check the response and return appropriate message
        if response.get("Response") == "Success":
            return {"result": "Call hung up successfully."}
        else:
            return {"error": response.get("Message", "Failed to hang up the call.")}

    except Exception as e:
        return {'error': str(e)}


class MakeCallView(APIView):
    def post(self, request):
        data = request.data
        ami_host = data.get('ami_host')
        ami_port = data.get('ami_port')
        ami_user = data.get('ami_user')
        ami_password = data.get('ami_password')
        from_extn = data.get('from_extn')
        to_extn = data.get('to_extn')

        result = one_to_one_call(ami_host, ami_port, ami_user, ami_password, from_extn, to_extn)

        return Response({"result": result}, status=status.HTTP_200_OK)


class HangupCallView(APIView):
    def post(self, request):
        # Extracting data from the request payload
        host = request.data.get("ami_host")
        port = request.data.get("ami_port")
        username = request.data.get('ami_user')
        password = request.data.get('ami_password')
        channel_id = request.data.get("channel_id")

        # Check if all required fields are present
        if not all([host, port, username, password, channel_id]):
            return Response({"error": "Host, port, username, password, and channel ID are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            # Connect to the Asterisk AMI
            ami = asterisk.manager.Manager()
            ami.connect(host, int(port))  # Convert port to integer
            ami.login(username, password)

            # Send the hangup action
            action = {
                'Action': 'Hangup',
                'Channel': channel_id
            }

            response = ami.send_action(action)
            ami.logoff()
            print(dir(response))
            print(response)

            # Check the response and return appropriate message
            if response.get("Response") == "Success":
                return Response({"result": "Call hung up successfully."}, status=status.HTTP_200_OK)
            else:
                return Response({"error": response.get("Message", "Failed to hang up the call.")},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateSIPConfiguration(APIView):
    def post(self, request):
        # Extract parameters from the request body if needed
        ip_zenitel = request.data.get("zenitel_ip", "10.30.250.212")
        sip_nick = request.data.get("sip_nick", "8002")
        sip_id = request.data.get("sip_id", "8002")
        sip_domain = request.data.get("sip_domain", "10.30.250.241")
        sip_auth_user = request.data.get("sip_auth_user", "8002")
        sip_auth_pwd = request.data.get("sip_auth_pwd", "8002")
        auto_answer_mode = request.data.get("auto_answer_mode", "on")

        # Define API endpoint and parameters
        url = f"http://{ip_zenitel}/goform/zForm_save_changes"
        params = {
            "sip_nick": sip_nick,
            "sip_id": sip_id,
            "sip_domain": sip_domain,
            "sipconfig": "SAVE",
            "sip_auth_user": sip_auth_user,
            "sip_auth_pwd": sip_auth_pwd,
            "auto_answer_mode": auto_answer_mode
        }

        # Send the request to the external API with basic authentication
        response = requests.get(url, params=params, auth=('admin', 'alphaadmin'))

        # Check if the request was successful
        if response.status_code == 200:
            return Response({"message": "SIP configuration updated successfully."}, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": "Failed to update configuration.", "status_code": response.status_code},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )