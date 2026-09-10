export function PasswordFields() {
  return <>
    <p id='password-policy'>Use at least 12 characters with letters and numbers. Avoid your username and common passwords. Choose a unique password different from your current password. Maximum 72 bytes; accented characters may use more than one byte.</p>
    <label>New password<input name='newPassword' type='password' autoComplete='new-password' required minLength={12} aria-describedby='password-policy' /></label>
    <label>Confirm new password<input name='confirmPassword' type='password' autoComplete='new-password' required minLength={12} /></label>
  </>
}
