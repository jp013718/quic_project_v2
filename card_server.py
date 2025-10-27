import argparse
import asyncio
import pandas
from PIL import Image
from requests import get

import aioquic.asyncio
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

class CardServer(aioquic.asyncio.QuicConnectionProtocol):  
  card_df = pandas.read_json('card_list.json')
  
  def quic_event_received(self, quic_event):
    if isinstance(quic_event, StreamDataReceived):
      data = quic_event.data.decode('utf-8')
      image = self.process_request(data)
      self._quic.send_stream_data(
        stream_id=quic_event.stream_id,
        data = image,
        end_stream=True,
      )
      self.transmit()

  
  def process_request(self, data):
    card = bytes(f"No card by the name '{data}' found...", encoding='utf-8')
    if data == '-r': 
      card_obj = self.card_df.sample()
      while '//' in card_obj["name"].values[0]:
        print("Oops, that card was double-sided")
        card_obj = self.card_df.sample()
      print(f"Sending over random card {card_obj["name"].values[0]}")
      card_url = card_obj["image_uris"].values[0]["large"]
      response = get(card_url, stream=True).raw
      with Image.open(response) as im:
        card = im.tobytes()
    else:
      print(f"Searching for card {data} in database")
      card_obj = self.card_df.loc[self.card_df["name"] == data]
      if not card_obj.empty:
        card_url = card_obj["image_uris"].values[0]["large"]
        response = get(card_url, stream=True).raw
        with Image.open(response) as im:
          card = im.tobytes()
    
    return card
      


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