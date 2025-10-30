import argparse
import asyncio
import pandas
from PIL import Image
from requests import get

import aioquic.asyncio
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

class CardServer(aioquic.asyncio.QuicConnectionProtocol):  
  # Read in the json list as a pandas dataframe
  card_df = pandas.read_json('card_list.json')
  
  # Handle a request
  def quic_event_received(self, quic_event):
    if isinstance(quic_event, StreamDataReceived):
      # Decode the request data
      data = quic_event.data.decode('utf-8')
      # Process the request
      image = self.process_request(data)
      # Send the processed image (or error message) to the client
      self._quic.send_stream_data(
        stream_id=quic_event.stream_id,
        data = image,
        end_stream=True,
      )
      self.transmit()

  
  def process_request(self, data):
    # Default the value of card to an error message. If a card isn't found matching the name in the request,
    # card will not change and the error message will be detected by the client. Also, add padding if the 
    # client is sending a bogus request to try to elicit the error message with a length matching a possible
    # card image.
    card = bytes(f"No card by the name '{data}' found...", encoding='utf-8')
    if len(card) == 1886976 or len(card) == 3773952:
      card += b' '
    
    # If a random card was requested, grab a sample from the database
    if data == '-r': 
      card_obj = self.card_df.sample()
      print(f"Sending over random card {card_obj["name"].values[0]}")
      # Handling double-faced cards
      if self.is_dfc(card_obj):
        card_front_url = list(card_obj["card_faces"].values)[0][0]["image_uris"]["large"]
        card_back_url = list(card_obj["card_faces"].values)[0][1]["image_uris"]["large"]
        card_front_response = get(card_front_url, stream=True).raw
        card_back_response = get(card_back_url, stream=True).raw
        with Image.open(card_front_response) as im:
          card_front = im.tobytes()
        with Image.open(card_back_response) as im:
          card_back = im.tobytes()
        card = card_front + card_back
      
      # Handling all other cards
      else:
        card_url = card_obj["image_uris"].values[0]["large"]
        response = get(card_url, stream=True).raw
        with Image.open(response) as im:
          card = im.tobytes()
    
    # If a random card wasn't requested, then search for the card by name
    else:
      print(f"Searching for card {data} in database")
      card_obj = self.card_df.loc[self.card_df["name"] == data]
      # Check that a card was found
      if not card_obj.empty:
        # Handling double-faced cards
        if self.is_dfc(card_obj):
          card_front_url = list(card_obj["card_faces"].values)[0][0]["image_uris"]["large"]
          card_back_url = list(card_obj["card_faces"].values)[0][1]["image_uris"]["large"]
          card_front_response = get(card_front_url, stream=True).raw
          card_back_response = get(card_back_url, stream=True).raw
          with Image.open(card_front_response) as im:
            card_front = im.tobytes()
          with Image.open(card_back_response) as im:
            card_back = im.tobytes()
          card = card_front + card_back
        
        # Handling all other cards
        else:
          card_url = card_obj["image_uris"].values[0]["large"]
          response = get(card_url, stream=True).raw
          with Image.open(response) as im:
            card = im.tobytes()
    
    return card
      
  def is_dfc(self, card_obj: pandas.DataFrame):
    return card_obj["layout"].values[0] == "transform" or card_obj["layout"].values[0] == "art_series" or card_obj["layout"].values[0] == "double_faced_token"


async def main(certfile, keyfile=None, password=None, host="127.0.0.1", port=9999):
  configuration = QuicConfiguration(is_client=False)
  configuration.load_cert_chain(certfile=certfile, keyfile=keyfile, password=password)
  server = await aioquic.asyncio.serve(
    host,
    port,
    configuration=configuration,
    create_protocol=CardServer,
  )

  loop = asyncio.get_running_loop()
  try:
    await loop.create_future()
  finally:
    server.close()


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('-c', '--certificate', required=True)
  parser.add_argument('-k', '--private-key')
  parser.add_argument('-p', '--port', type=int, default=9999)
  args = parser.parse_args()

  asyncio.run(
    main(
      certfile=args.certificate,
      keyfile=args.private_key,
      port=args.port,
    )
  )