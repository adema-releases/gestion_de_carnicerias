from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from gestion_de_carnicerias import admin_override
from gestion_de_carnicerias.admin_override import FACTORY_RESET_CONFIRMATION_PHRASE, reset_database_to_factory


class FactoryResetViewTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.superuser = user_model.objects.create_superuser(
			username='root',
			email='root@example.com',
			password='testpass123',
		)
		self.staff_user = user_model.objects.create_user(
			username='staff',
			email='staff@example.com',
			password='testpass123',
			is_staff=True,
		)
		self.url = reverse('admin_factory_reset')

	@patch('gestion_de_carnicerias.admin_override.reset_database_to_factory')
	def test_requires_exact_confirmation_phrase(self, mock_reset):
		self.client.force_login(self.superuser)

		response = self.client.post(
			self.url,
			{'confirmation_phrase': 'otra frase', 'superuser_password': 'testpass123'},
		)

		self.assertEqual(response.status_code, 400)
		mock_reset.assert_not_called()

	@patch('gestion_de_carnicerias.admin_override.reset_database_to_factory')
	def test_requires_valid_superuser_password(self, mock_reset):
		self.client.force_login(self.superuser)

		response = self.client.post(
			self.url,
			{'confirmation_phrase': FACTORY_RESET_CONFIRMATION_PHRASE, 'superuser_password': 'incorrecta'},
		)

		self.assertEqual(response.status_code, 400)
		mock_reset.assert_not_called()

	@patch('gestion_de_carnicerias.admin_override.reset_database_to_factory')
	def test_only_superuser_can_reset(self, mock_reset):
		self.client.force_login(self.staff_user)

		response = self.client.post(
			self.url,
			{'confirmation_phrase': FACTORY_RESET_CONFIRMATION_PHRASE, 'superuser_password': 'testpass123'},
		)

		self.assertEqual(response.status_code, 403)
		mock_reset.assert_not_called()

	@patch('gestion_de_carnicerias.admin_override.reset_database_to_factory')
	def test_successful_reset_returns_completion_page(self, mock_reset):
		self.client.force_login(self.superuser)

		response = self.client.post(
			self.url,
			{'confirmation_phrase': FACTORY_RESET_CONFIRMATION_PHRASE, 'superuser_password': 'testpass123'},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Base reinicializada')
		mock_reset.assert_called_once_with()

	def test_admin_index_renders_factory_reset_modal_for_superuser(self):
		self.client.force_login(self.superuser)

		response = self.client.get(reverse('admin:index'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Resetear de fabrica')
		self.assertContains(response, '/admin/system/factory-reset/')
		self.assertContains(response, 'js/admin-factory-reset.js')

	def test_admin_index_hides_factory_reset_link_for_staff_without_permission(self):
		self.client.force_login(self.staff_user)

		response = self.client.get(reverse('admin:index'))

		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, 'Resetear de fabrica')


class FactoryResetHelperTests(TestCase):
	@patch('gestion_de_carnicerias.admin_override.connections.close_all')
	@patch('gestion_de_carnicerias.admin_override.call_command')
	def test_reset_database_to_factory_deletes_sqlite_file_and_runs_init(self, mock_call_command, mock_close_all):
		with TemporaryDirectory() as temp_dir:
			database_path = Path(temp_dir) / 'factory-reset.sqlite3'
			database_path.write_text('placeholder', encoding='utf-8')

			with patch.object(
				admin_override.settings,
				'DATABASES',
				{
					'default': {
						'ENGINE': 'django.db.backends.sqlite3',
						'NAME': str(database_path),
					}
				},
			):
				reset_database_to_factory()

			mock_close_all.assert_called_once_with()
			mock_call_command.assert_called_once_with('init_system', verbosity=1)
			self.assertFalse(database_path.exists())
