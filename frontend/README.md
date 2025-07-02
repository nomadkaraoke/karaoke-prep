# Karaoke Generator Frontend

This is the static frontend for the Karaoke Generator web application. It's designed to be deployed on GitHub Pages with a custom domain.

## Architecture

- **Frontend**: Static HTML/CSS/JS hosted on GitHub Pages → `gen.nomadkaraoke.com`
- **Backend**: Modal API endpoints → `nomadkaraoke--karaoke-generator-webapp-web-endpoint.modal.run/api`

## Files

- `index.html` - Main application page
- `styles.css` - All CSS styles and responsive design
- `app.js` - JavaScript application logic and API communication
- `README.md` - This file

## Features

- 🎵 YouTube URL submission for karaoke generation
- 📊 Real-time job monitoring with progress bars
- 📋 Comprehensive logging and admin controls
- 📝 Lyrics review interface
- 📥 Video download functionality
- 🔧 Admin panel for job management
- 📱 Responsive mobile design

## Deployment to GitHub Pages

### 1. Create GitHub Repository

```bash
# Initialize git repository
cd frontend
git init
git add .
git commit -m "Initial frontend setup"

# Create GitHub repository and push
git remote add origin https://github.com/YOUR_USERNAME/karaoke-gen-frontend.git
git branch -M main
git push -u origin main
```

### 2. Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** tab
3. Scroll to **Pages** section
4. Under **Source**, select **Deploy from a branch**
5. Choose **main** branch and **/ (root)** folder
6. Click **Save**

### 3. Configure Custom Domain

1. In the **Pages** section, add your custom domain: `gen.nomadkaraoke.com`
2. Enable **Enforce HTTPS**

### 4. DNS Configuration (Cloudflare)

Add a CNAME record in your Cloudflare DNS:

```
Type: CNAME
Name: gen
Target: YOUR_USERNAME.github.io
Proxy status: Proxied (orange cloud)
```

## Development

### Local Testing

You can test the frontend locally using Python's built-in server:

```bash
cd frontend
python -m http.server 8000
```

Then visit `http://localhost:8000`

### API Configuration

The API endpoint is configured in `app.js`:

```javascript
const API_BASE_URL = 'https://nomadkaraoke--karaoke-generator-webapp-web-endpoint.modal.run/api';
```

Update this URL if your Modal deployment changes.

## Features Overview

### Job Management
- Submit YouTube URLs for processing
- Monitor job progress in real-time
- View detailed logs for each job
- Delete, retry, or download completed jobs

### Admin Controls
- Clear error jobs in bulk
- Export all logs as JSON
- Real-time statistics dashboard
- Auto-refresh functionality

### Responsive Design
- Mobile-friendly interface
- Progressive enhancement
- Modern CSS with gradients and animations
- Accessible design patterns

## Browser Support

- Chrome/Chromium 80+
- Firefox 75+
- Safari 13+
- Edge 80+

## Security Notes

- CORS is configured on the backend to allow requests from your domain
- All API communication uses HTTPS
- No sensitive data is stored in the frontend
- GitHub Pages provides automatic HTTPS with custom domains

## Troubleshooting

### API Connection Issues
1. Check that the Modal backend is running
2. Verify the API_BASE_URL in app.js
3. Check browser console for CORS errors

### GitHub Pages Not Updating
1. Check the Actions tab for deployment status
2. Ensure all files are committed and pushed
3. Wait 5-10 minutes for propagation

### Custom Domain Issues
1. Verify DNS settings in Cloudflare
2. Ensure CNAME record points to YOUR_USERNAME.github.io
3. Enable HTTPS enforcement in GitHub Pages settings 