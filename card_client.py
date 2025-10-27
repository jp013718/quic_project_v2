import argparse
import asyncio
import ssl

import aioquic.asyncio
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

from PIL import Image

class CardClient(aioquic.asyncio.QuicConnectionProtocol):
  stream_buffers = {}
  images = []
  
  def quic_event_received(self, quic_event):
    if isinstance(quic_event, StreamDataReceived):
      data = quic_event.data
      if self.stream_buffers[quic_event.stream_id]:
        self.stream_buffers[quic_event.stream_id] += data
      else:
        self.stream_buffers[quic_event.stream_id] = data

      if quic_event.end_stream:
        self.process_images(quic_event.stream_id)
        if not self.stream_buffers:
          self.time.set_result(self._loop.time() - self.start_time)

  def transfer(self, data):
    stream_id = self._quic.get_next_available_stream_id()
    self._quic.send_stream_data(
      stream_id=stream_id,
      data=bytes(data, encoding='utf-8'),
      end_stream=True,
    )
    self.stream_buffers[stream_id] = None
    self.transmit()

  def process_images(self, stream_id):
    img_bytes = self.stream_buffers[stream_id]
    try:
      image = Image.frombytes("RGB", (672, 936), img_bytes)
      image.show()
    except ValueError as e:
      error = img_bytes.decode('utf-8')
      print(error)
    finally:
      del self.stream_buffers[stream_id]

  def process_arguments(self, data):
    for card_name in data[0]:
      self.transfer(card_name)
    for _ in range(data[1]):
      self.transfer('-r')

    self.start_time = self._loop.time()
    self.time = self._loop.create_future()
    return self.time
    

async def main(data, host='127.0.0.1', port=9999):
  async with aioquic.asyncio.connect(
    host,
    port,
    configuration=QuicConfiguration(verify_mode=ssl.CERT_NONE),
    create_protocol=CardClient,
  ) as client:
    await client.process_arguments(data)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('-H', '--host', type=str, default='127.0.0.1')
  parser.add_argument('-p', '--port', type=int, default=9999)
  parser.add_argument('-n', '--name', nargs='+', action='extend', type=str, default=[])
  parser.add_argument('-r', '--random', type=int, default=0)
  args = parser.parse_args()

  host = args.host
  port = args.port
  card_names = args.name
  n_random_cards = args.random

  data = (card_names, n_random_cards)

  asyncio.run(
    main(
      data,
      host,
      port,
    )
  )