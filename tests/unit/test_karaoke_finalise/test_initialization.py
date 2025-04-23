import pytest
import logging
import os
from unittest.mock import MagicMock, patch

# Update imports to use refactored classes
from karaoke_prep.karaoke_finalise.karaoke_finalise import KaraokeFinalise
from karaoke_prep.karaoke_finalise.file_manager import FileManager
from karaoke_prep.karaoke_finalise.media_processor import MediaProcessor
from karaoke_prep.karaoke_finalise.user_interface import UserInterface
from karaoke_prep.karaoke_finalise.youtube_manager import YouTubeManager
from karaoke_prep.karaoke_finalise.format_generator import FormatGenerator
from karaoke_prep.karaoke_finalise.notifier import Notifier
from karaoke_prep.karaoke_finalise.cloud_manager import CloudManager

# Configuration used in tests - updated to match the new constructor parameters
MINIMAL_CONFIG = {
    "dry_run": False,
    "instrumental_format": "flac",
    "enable_cdg": False,
    "enable_txt": False,
    "brand_prefix": None,
    "organised_dir": None,
    "organised_dir_rclone_root": None,
    "public_share_dir": None,
    "youtube_client_secrets_file": None,
    "youtube_description_file": None,
    "rclone_destination": None,
    "discord_webhook_url": None,
    "email_template_file": None,
    "cdg_styles": None,
    "keep_brand_code": False,
    "non_interactive": False,
}

@pytest.fixture
def mock_logger():
    """Fixture for a mocked logger."""
    logger = MagicMock()
    return logger

@pytest.fixture
def basic_finaliser(mock_logger):
    """Fixture for a basic KaraokeFinalise instance."""
    finaliser = KaraokeFinalise(logger=mock_logger, **MINIMAL_CONFIG)
    return finaliser

@pytest.fixture
def mock_file_manager():
    """Fixture for a mocked FileManager."""
    return MagicMock(spec=FileManager)

@pytest.fixture
def mock_media_processor():
    """Fixture for a mocked MediaProcessor."""
    return MagicMock(spec=MediaProcessor)

@pytest.fixture
def mock_user_interface():
    """Fixture for a mocked UserInterface."""
    return MagicMock(spec=UserInterface)

@pytest.fixture
def mock_youtube_manager():
    """Fixture for a mocked YouTubeManager."""
    return MagicMock(spec=YouTubeManager)

@pytest.fixture
def mock_format_generator():
    """Fixture for a mocked FormatGenerator."""
    return MagicMock(spec=FormatGenerator)

@pytest.fixture
def mock_notifier():
    """Fixture for a mocked Notifier."""
    return MagicMock(spec=Notifier)

@pytest.fixture
def mock_cloud_manager():
    """Fixture for a mocked CloudManager."""
    return MagicMock(spec=CloudManager)

def test_init_defaults(mock_logger):
    """Test KaraokeFinalise initializes with default values correctly."""
    finaliser = KaraokeFinalise(logger=mock_logger, **MINIMAL_CONFIG)
    
    # Verify component managers are initialized
    assert hasattr(finaliser, 'file_manager')
    assert hasattr(finaliser, 'media_processor')
    assert hasattr(finaliser, 'user_interface')
    assert hasattr(finaliser, 'youtube_manager')
    assert hasattr(finaliser, 'format_generator')
    assert hasattr(finaliser, 'notifier')
    assert hasattr(finaliser, 'cloud_manager')
    assert hasattr(finaliser, 'suffixes')  # The new attribute we added
    
    # Verify basic attributes
    assert finaliser.dry_run == MINIMAL_CONFIG["dry_run"]
    assert finaliser.instrumental_format == MINIMAL_CONFIG["instrumental_format"]
    assert finaliser.enable_cdg == MINIMAL_CONFIG["enable_cdg"]
    assert finaliser.enable_txt == MINIMAL_CONFIG["enable_txt"]
    assert finaliser.brand_prefix == MINIMAL_CONFIG["brand_prefix"]
    assert finaliser.non_interactive == MINIMAL_CONFIG["non_interactive"]

def test_init_uses_component_managers(mock_logger):
    """Test that KaraokeFinalise initializes and uses the component managers."""
    with patch('karaoke_prep.karaoke_finalise.karaoke_finalise.FileManager') as mock_file_manager_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.MediaProcessor') as mock_media_processor_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.UserInterface') as mock_user_interface_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.YouTubeManager') as mock_youtube_manager_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.FormatGenerator') as mock_format_generator_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.Notifier') as mock_notifier_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.CloudManager') as mock_cloud_manager_class:
        
        # Create mocks for the component instances
        mock_file_manager_instance = MagicMock()
        mock_file_manager_instance.suffixes = {"key": "value"}  # Mock suffixes
        mock_media_processor_instance = MagicMock()
        mock_user_interface_instance = MagicMock()
        mock_youtube_manager_instance = MagicMock()
        mock_format_generator_instance = MagicMock()
        mock_notifier_instance = MagicMock()
        mock_cloud_manager_instance = MagicMock()
        
        # Configure the mock classes to return the mock instances
        mock_file_manager_class.return_value = mock_file_manager_instance
        mock_media_processor_class.return_value = mock_media_processor_instance
        mock_user_interface_class.return_value = mock_user_interface_instance
        mock_youtube_manager_class.return_value = mock_youtube_manager_instance
        mock_format_generator_class.return_value = mock_format_generator_instance
        mock_notifier_class.return_value = mock_notifier_instance
        mock_cloud_manager_class.return_value = mock_cloud_manager_instance
        
        # Initialize KaraokeFinalise
        finaliser = KaraokeFinalise(logger=mock_logger, **MINIMAL_CONFIG)
        
        # Verify component managers were initialized with correct parameters
        mock_file_manager_class.assert_called_once()
        mock_media_processor_class.assert_called_once()
        mock_user_interface_class.assert_called_once()
        mock_youtube_manager_class.assert_called_once()
        mock_format_generator_class.assert_called_once()
        mock_notifier_class.assert_called_once()
        mock_cloud_manager_class.assert_called_once()
        
        # Verify component managers were assigned correctly
        assert finaliser.file_manager is mock_file_manager_instance
        assert finaliser.media_processor is mock_media_processor_instance
        assert finaliser.user_interface is mock_user_interface_instance
        assert finaliser.youtube_manager is mock_youtube_manager_instance
        assert finaliser.format_generator is mock_format_generator_instance
        assert finaliser.notifier is mock_notifier_instance
        assert finaliser.cloud_manager is mock_cloud_manager_instance
        
        # Verify suffixes were assigned correctly
        assert finaliser.suffixes == mock_file_manager_instance.suffixes

def test_init_custom_logger_setup():
    """Test KaraokeFinalise can be initialized with a custom logger."""
    custom_logger = logging.getLogger("custom_logger")
    finaliser = KaraokeFinalise(logger=custom_logger, **MINIMAL_CONFIG)
    assert finaliser.logger is custom_logger

def test_component_manager_parameter_passing(mock_logger):
    """Test that parameters are correctly passed to component managers."""
    with patch('karaoke_prep.karaoke_finalise.karaoke_finalise.FileManager') as mock_file_manager_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.MediaProcessor') as mock_media_processor_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.UserInterface') as mock_user_interface_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.YouTubeManager') as mock_youtube_manager_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.FormatGenerator') as mock_format_generator_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.Notifier') as mock_notifier_class, \
         patch('karaoke_prep.karaoke_finalise.karaoke_finalise.CloudManager') as mock_cloud_manager_class:
        
        # Initialize KaraokeFinalise with configuration
        test_config = MINIMAL_CONFIG.copy()
        test_config.update({
            'dry_run': True,
            'non_interactive': True,
            'brand_prefix': 'TEST',
            'organised_dir': '/path/to/org',
            'public_share_dir': '/path/to/public',
            'youtube_client_secrets_file': 'secrets.json',
            'youtube_description_file': 'desc.txt',
            'discord_webhook_url': 'https://discord.com/webhook',
            'email_template_file': 'email.txt',
            'cdg_styles': {'style': 'test'},
        })
        
        finaliser = KaraokeFinalise(logger=mock_logger, **test_config)
        
        # Verify FileManager was initialized with correct parameters
        mock_file_manager_class.assert_called_once_with(
            logger=mock_logger,
            dry_run=True,
            brand_prefix='TEST',
            organised_dir='/path/to/org',
            public_share_dir='/path/to/public',
            keep_brand_code=False
        )
        
        # Verify MediaProcessor was initialized with correct parameters
        mock_media_processor_class.assert_called_once_with(
            logger=mock_logger,
            dry_run=True,
            log_level=logging.DEBUG,
            non_interactive=True
        )
        
        # Verify UserInterface was initialized with correct parameters
        mock_user_interface_class.assert_called_once_with(
            logger=mock_logger,
            non_interactive=True
        )
        
        # Verify YouTubeManager was initialized with correct parameters
        mock_youtube_manager_class.assert_called_once_with(
            logger=mock_logger,
            dry_run=True,
            youtube_client_secrets_file='secrets.json',
            youtube_description_file='desc.txt',
            non_interactive=True
        )
        
        # Verify FormatGenerator was initialized with correct parameters
        mock_format_generator_class.assert_called_once_with(
            logger=mock_logger,
            dry_run=True,
            cdg_styles={'style': 'test'}
        )
        
        # Verify Notifier was initialized with correct parameters
        mock_notifier_class.assert_called_once_with(
            logger=mock_logger,
            dry_run=True,
            discord_webhook_url='https://discord.com/webhook',
            email_template_file='email.txt',
            youtube_client_secrets_file='secrets.json'
        )
        
        # Verify CloudManager was initialized with correct parameters
        mock_cloud_manager_class.assert_called_once_with(
            logger=mock_logger,
            dry_run=True,
            public_share_dir='/path/to/public',
            rclone_destination='None',  # This is None in test_config
            organised_dir_rclone_root=None
        )

def test_validate_input_parameters_for_features(basic_finaliser):
    """Test that validate_input_parameters_for_features delegates to UserInterface."""
    # Replace with mocks
    basic_finaliser.user_interface = MagicMock()
    mock_features = {
        "youtube_upload_enabled": True,
        "discord_notication_enabled": True,
        "folder_organisation_enabled": True,
        "public_share_copy_enabled": True,
        "public_share_rclone_enabled": True
    }
    basic_finaliser.user_interface.validate_input_parameters_for_features.return_value = mock_features
    
    # Call the method
    basic_finaliser.validate_input_parameters_for_features()
    
    # Verify the appropriate method was called
    basic_finaliser.user_interface.validate_input_parameters_for_features.assert_called_once_with(
        youtube_client_secrets_file=basic_finaliser.youtube_client_secrets_file,
        youtube_description_file=basic_finaliser.youtube_description_file,
        discord_webhook_url=basic_finaliser.discord_webhook_url,
        brand_prefix=basic_finaliser.brand_prefix,
        organised_dir=basic_finaliser.organised_dir,
        public_share_dir=basic_finaliser.public_share_dir,
        rclone_destination=basic_finaliser.rclone_destination,
        enable_cdg=basic_finaliser.enable_cdg,
        enable_txt=basic_finaliser.enable_txt
    )
    
    # Verify feature flags were set correctly
    assert basic_finaliser.youtube_upload_enabled == mock_features["youtube_upload_enabled"]
    assert basic_finaliser.discord_notication_enabled == mock_features["discord_notication_enabled"]
    assert basic_finaliser.folder_organisation_enabled == mock_features["folder_organisation_enabled"]
    assert basic_finaliser.public_share_copy_enabled == mock_features["public_share_copy_enabled"]
    assert basic_finaliser.public_share_rclone_enabled == mock_features["public_share_rclone_enabled"]

def test_execute_optional_features(basic_finaliser):
    """Test that execute_optional_features delegates to the appropriate managers."""
    # Setup mocks
    basic_finaliser.youtube_manager = MagicMock()
    basic_finaliser.notifier = MagicMock()
    basic_finaliser.file_manager = MagicMock()
    basic_finaliser.cloud_manager = MagicMock()
    
    # Enable features
    basic_finaliser.youtube_upload_enabled = True
    basic_finaliser.discord_notication_enabled = True
    basic_finaliser.folder_organisation_enabled = True
    basic_finaliser.public_share_copy_enabled = True
    basic_finaliser.public_share_rclone_enabled = True
    
    # Call the method
    artist = "Test Artist"
    title = "Test Title"
    base_name = "Test Artist - Test Title"
    input_files = {"key": "value"}
    output_files = {"key": "value"}
    
    basic_finaliser.execute_optional_features(artist, title, base_name, input_files, output_files)
    
    # Verify the appropriate methods were called
    basic_finaliser.youtube_manager.upload_final_mp4_to_youtube_with_title_thumbnail.assert_called_once()
    basic_finaliser.notifier.post_discord_notification.assert_called_once()
    basic_finaliser.file_manager.get_next_brand_code.assert_called_once()
    basic_finaliser.file_manager.move_files_to_brand_code_folder.assert_called_once()
    basic_finaliser.file_manager.copy_final_files_to_public_share_dirs.assert_called_once()
    basic_finaliser.cloud_manager.sync_public_share_dir_to_rclone_destination.assert_called_once()
    basic_finaliser.cloud_manager.generate_organised_folder_sharing_link.assert_called_once()

def test_process(basic_finaliser):
    """Test that process delegates to the appropriate managers."""
    # Setup mocks
    basic_finaliser.user_interface = MagicMock()
    basic_finaliser.file_manager = MagicMock()
    basic_finaliser.media_processor = MagicMock()
    basic_finaliser.format_generator = MagicMock()
    
    # Mock file_manager methods to return expected values
    mock_with_vocals_file = "Artist - Title (With Vocals).mov"
    mock_base_name = "Artist - Title"
    mock_artist = "Artist"
    mock_title = "Title"
    mock_instrumental_file = "Artist - Title (Instrumental).flac"
    mock_input_files = {"key": "value"}
    mock_output_files = {"key": "value"}
    
    basic_finaliser.file_manager.find_with_vocals_file.return_value = mock_with_vocals_file
    basic_finaliser.file_manager.get_names_from_withvocals.return_value = (mock_base_name, mock_artist, mock_title)
    basic_finaliser.file_manager.choose_instrumental_audio_file.return_value = mock_instrumental_file
    basic_finaliser.file_manager.check_input_files_exist.return_value = mock_input_files
    basic_finaliser.file_manager.prepare_output_filenames.return_value = mock_output_files
    
    # Replace execute_optional_features with a mock
    basic_finaliser.execute_optional_features = MagicMock()
    
    # Enable features for testing
    basic_finaliser.enable_cdg = True
    basic_finaliser.enable_txt = True
    
    # Call the method
    result = basic_finaliser.process()
    
    # Verify the appropriate methods were called
    basic_finaliser.validate_input_parameters_for_features.assert_called_once()
    basic_finaliser.file_manager.find_with_vocals_file.assert_called_once()
    basic_finaliser.file_manager.get_names_from_withvocals.assert_called_once_with(mock_with_vocals_file)
    basic_finaliser.file_manager.choose_instrumental_audio_file.assert_called_once()
    basic_finaliser.file_manager.check_input_files_exist.assert_called_once()
    basic_finaliser.file_manager.prepare_output_filenames.assert_called_once()
    
    basic_finaliser.format_generator.create_cdg_zip_file.assert_called_once()
    basic_finaliser.format_generator.create_txt_zip_file.assert_called_once()
    basic_finaliser.media_processor.remux_and_encode_output_video_files.assert_called_once()
    basic_finaliser.execute_optional_features.assert_called_once()
    
    # Verify result contains expected fields
    assert "artist" in result
    assert "title" in result
    assert "youtube_url" in result
    assert "brand_code" in result
