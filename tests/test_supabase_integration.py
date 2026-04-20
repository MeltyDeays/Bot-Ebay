import unittest

from supabase_integration import AnalizadorRentabilidad, AnalizadorVisual


class FakeResponse:
    def __init__(self, status_code, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({
            'url': url,
            'headers': headers,
            'json': json,
            'timeout': timeout,
        })
        return self.response


class StaticSessionProvider:
    def __init__(self, session):
        self.session = session

    def get(self):
        return self.session


class FakeSupabase:
    def __init__(self):
        self.calls = 0

    def select(self, table, filters='', limit=100):
        self.calls += 1
        return [
            {
                'titulo_marketplace': 'Lenovo ThinkPad E14',
                'precio_nic_usd': 420,
                'condicion': 'Usado',
                'ciudad': 'Managua',
            }
        ]


class SupabaseIntegrationTests(unittest.TestCase):
    def test_visual_payload_never_exceeds_five_images(self):
        analyzer = AnalizadorVisual(
            'test-key',
            few_shot_examples=[
                {
                    'prompt': 'Ejemplo malo',
                    'assistant': 'Debe salir bajo.',
                    'url': 'data:image/png;base64,bad',
                },
                {
                    'prompt': 'Ejemplo bueno',
                    'assistant': 'Debe salir alto.',
                    'url': 'data:image/png;base64,good',
                },
            ],
        )

        payload, metadata = analyzer.build_request_payload(
            [
                'https://i.ebayimg.com/images/g/a.jpg',
                'https://i.ebayimg.com/images/g/a.jpg',
                'https://i.ebayimg.com/images/g/b.jpg',
                'https://i.ebayimg.com/images/g/c.jpg',
                'https://i.ebayimg.com/images/g/d.jpg',
            ],
            'Lenovo ThinkPad',
            'Used',
        )

        total_images = 0
        for message in payload['messages']:
            content = message.get('content')
            if not isinstance(content, list):
                continue
            total_images += sum(1 for item in content if item.get('type') == 'image_url')

        self.assertLessEqual(total_images, 5)
        self.assertEqual(metadata['few_shot_example_count'], 2)
        self.assertEqual(metadata['product_image_count'], 3)
        self.assertEqual(metadata['total_image_count'], 5)

    def test_visual_provider_error_returns_structured_payload(self):
        session = FakeSession(FakeResponse(413, text='payload too large'))
        analyzer = AnalizadorVisual(
            'test-key',
            session_provider=StaticSessionProvider(session),
            few_shot_examples=[],
        )

        result = analyzer.analizar_imagen(
            ['https://i.ebayimg.com/images/g/test.jpg'],
            'Lenovo ThinkPad',
            'Minor scratches',
        )

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'provider_http_error')
        self.assertEqual(result['provider_status'], 413)
        self.assertEqual(result['score'], 50)
        self.assertEqual(result['calidad_visual'], 'error_api')
        self.assertEqual(len(session.calls), 1)

    def test_rentabilidad_reference_cache_reuses_supabase_reads_within_ttl(self):
        fake_supabase = FakeSupabase()
        fake_time = [1000.0]
        analyzer = AnalizadorRentabilidad(
            '',
            supabase=fake_supabase,
            cache_ttl_seconds=300,
            time_fn=lambda: fake_time[0],
        )

        first = analyzer.buscar_referencias_reales('Lenovo ThinkPad', 'laptop')
        second = analyzer.buscar_referencias_reales('Dell Latitude', 'laptop')

        self.assertEqual(fake_supabase.calls, 1)
        self.assertEqual(first, second)

        fake_time[0] += 301
        analyzer.buscar_referencias_reales('HP EliteBook', 'laptop')
        self.assertEqual(fake_supabase.calls, 2)


if __name__ == '__main__':
    unittest.main()
