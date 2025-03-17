class KaraokeGenError(Exception):
    """Base exception for all karaoke generator errors"""
    pass


class MediaError(KaraokeGenError):
    """Exception raised for errors related to media handling"""
    pass


class DownloadError(MediaError):
    """Exception raised when a download fails"""
    pass


class ConversionError(MediaError):
    """Exception raised when a media conversion fails"""
    pass


class LyricsError(KaraokeGenError):
    """Exception raised for errors related to lyrics processing"""
    pass


class LyricsFetchError(LyricsError):
    """Exception raised when lyrics fetching fails"""
    pass


class TranscriptionError(LyricsError):
    """Exception raised when lyrics transcription fails"""
    pass


class AudioError(KaraokeGenError):
    """Exception raised for errors related to audio processing"""
    pass


class SeparationError(AudioError):
    """Exception raised when audio separation fails"""
    pass


class NormalizationError(AudioError):
    """Exception raised when audio normalization fails"""
    pass


class VideoError(KaraokeGenError):
    """Exception raised for errors related to video processing"""
    pass


class RenderingError(VideoError):
    """Exception raised when video rendering fails"""
    pass


class DistributionError(KaraokeGenError):
    """Exception raised for errors related to distribution"""
    pass


class YouTubeError(DistributionError):
    """Exception raised when YouTube operations fail"""
    pass


class UserCancellationError(KaraokeGenError):
    """Exception raised when the user cancels an operation"""
    pass 